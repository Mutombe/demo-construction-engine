"""AI inbox pipeline: upload → extract (one vision call) → normalize/validate/draft/gate.

The model only ever fills `extraction`; the deterministic pipeline below turns it
into `proposed_action`. Posting real records happens exclusively in posting.py on
human approval.
"""

import base64
import hashlib
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import (
    ExpenseCategory,
    IngestionDocType,
    IngestionStatus,
    PoStatus,
    ProjectStatus,
    RfqStatus,
)
from app.core.config import settings
from app.core.exceptions import (
    AiRateLimitedError,
    AiUpstreamError,
    ConflictError,
    NotFoundError,
    ValidationFailedError,
)
from app.modules.ai import client as ai_client
from app.modules.ai.service import _check_refusal, _map_ai_errors
from app.modules.ingestion import prompts
from app.modules.ingestion.extraction import DocumentExtraction
from app.modules.ingestion.models import IngestionItem
from app.modules.procurement.models import PurchaseOrder, Quote, Rfq, Supplier
from app.modules.projects.models import Project

ALLOWED_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}
MAX_FILE_SIZE = 15 * 1024 * 1024

# Weakest-link gate: the draft auto-passes only if EVERY required field (and the
# classification itself) is high-confidence. Human corrections count as 1.0.
CONFIDENCE_SCORES = {"high": 0.98, "medium": 0.80, "low": 0.50}
GATE_THRESHOLD = 0.95


# --- Storage + upload -------------------------------------------------------


def _media_root() -> Path:
    return Path(settings.media_root)


def resolve_file_path(item: IngestionItem) -> Path:
    path = (_media_root() / item.file_path).resolve()
    if not path.is_file():
        raise NotFoundError("Stored file is missing")
    return path


def save_upload(
    db: Session,
    *,
    filename: str,
    content: bytes,
    media_type: str,
    project_id: uuid.UUID | None,
    user_id: uuid.UUID,
) -> tuple[IngestionItem, list[uuid.UUID]]:
    if media_type not in ALLOWED_TYPES:
        raise ValidationFailedError("Only JPEG, PNG, WebP images and PDF files are accepted")
    if len(content) == 0:
        raise ValidationFailedError("The uploaded file is empty")
    if len(content) > MAX_FILE_SIZE:
        raise ValidationFailedError("File exceeds the 15 MB limit")
    if project_id is not None and db.get(Project, project_id) is None:
        raise ValidationFailedError("Project hint does not exist")

    sha = hashlib.sha256(content).hexdigest()
    duplicate_ids = list(
        db.scalars(select(IngestionItem.id).where(IngestionItem.file_sha256 == sha))
    )

    item = IngestionItem(
        project_id=project_id,
        original_filename=filename[:255],
        file_path="",  # set below once the id exists
        file_sha256=sha,
        media_type=media_type,
        file_size=len(content),
        created_by=user_id,
    )
    db.add(item)
    db.flush()

    today = date.today()
    rel = Path("ingestion") / f"{today.year:04d}" / f"{today.month:02d}"
    rel_file = rel / f"{item.id}{ALLOWED_TYPES[media_type]}"
    target = _media_root() / rel_file
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    item.file_path = rel_file.as_posix()
    db.flush()
    return item, duplicate_ids


# --- Listing / lookup -------------------------------------------------------


def get_item(db: Session, item_id: uuid.UUID) -> IngestionItem:
    item = db.get(IngestionItem, item_id)
    if item is None:
        raise NotFoundError("Ingestion item not found")
    return item


def list_items(
    db: Session,
    page: int,
    page_size: int,
    status: IngestionStatus | None = None,
    doc_type: IngestionDocType | None = None,
    project_id: uuid.UUID | None = None,
) -> tuple[list[IngestionItem], int]:
    query = select(IngestionItem)
    if status is not None:
        query = query.where(IngestionItem.status == status)
    if doc_type is not None:
        query = query.where(IngestionItem.doc_type == doc_type)
    if project_id is not None:
        query = query.where(IngestionItem.project_id == project_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = list(
        db.scalars(
            query.order_by(IngestionItem.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return items, total


# --- Context for the extraction call ----------------------------------------


def _build_context(db: Session, item: IngestionItem) -> str:
    parts: list[str] = []

    projects = list(
        db.scalars(
            select(Project)
            .where(Project.status.in_([ProjectStatus.planning, ProjectStatus.active]))
            .order_by(Project.created_at.desc())
            .limit(50)
        )
    )
    parts.append(
        "PROJECTS (match project_match against these codes):\n"
        + "\n".join(f"- {p.code} | {p.name}" for p in projects)
    )

    suppliers = list(
        db.scalars(
            select(Supplier)
            .where(Supplier.is_active.is_(True))
            .order_by(Supplier.name)
            .limit(100)
        )
    )
    parts.append("KNOWN SUPPLIERS:\n" + "\n".join(f"- {s.name}" for s in suppliers))

    pos = list(
        db.scalars(
            select(PurchaseOrder)
            .where(PurchaseOrder.status == PoStatus.issued)
            .order_by(PurchaseOrder.created_at.desc())
            .limit(20)
        )
    )
    po_lines = []
    for po in pos:
        lines = "; ".join(f"{i.description} x{i.quantity}{i.unit or ''}" for i in po.items[:10])
        po_lines.append(f"- {po.doc_number} | supplier: {po.supplier.name} | {lines}")
    parts.append(
        "OPEN PURCHASE ORDERS (match po_match against these numbers):\n" + "\n".join(po_lines)
    )

    rfqs = list(
        db.scalars(
            select(Rfq)
            .where(Rfq.status == RfqStatus.issued)
            .order_by(Rfq.created_at.desc())
            .limit(10)
        )
    )
    rfq_lines = []
    for rfq in rfqs:
        lines = "; ".join(
            f"[{i.id}] {i.description} ({i.quantity} {i.unit})" for i in rfq.items[:15]
        )
        rfq_lines.append(f"- {rfq.doc_number} | {rfq.title} | lines: {lines}")
    parts.append(
        "OPEN RFQS (match rfq_match against these numbers; use [id] for rfq_item_id):\n"
        + "\n".join(rfq_lines)
    )

    if item.project_id is not None:
        hint = db.get(Project, item.project_id)
        if hint is not None:
            parts.append(
                f"UPLOADER HINT: this document likely belongs to project "
                f"{hint.code} — {hint.name}."
            )
    parts.append(f"Original filename: {item.original_filename}")
    parts.append("Classify and extract this document.")
    return "\n\n".join(parts)


def _media_block(item: IngestionItem, content: bytes) -> dict:
    data = base64.standard_b64encode(content).decode("ascii")
    if item.media_type == "application/pdf":
        return {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": data},
        }
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": item.media_type, "data": data},
    }


# --- Process (the only AI call in this module) ------------------------------


def process_item(db: Session, item_id: uuid.UUID) -> IngestionItem:
    item = get_item(db, item_id)
    if item.status not in (IngestionStatus.received, IngestionStatus.failed):
        raise ConflictError("Only received or failed items can be processed")

    content = resolve_file_path(item).read_bytes()
    context = _build_context(db, item)

    try:
        with _map_ai_errors():
            response = ai_client.get_client().messages.parse(
                model=ai_client.MODEL,
                max_tokens=16000,
                output_config={"effort": "medium"},
                system=prompts.INGESTION_SYSTEM,
                messages=[
                    {
                        "role": "user",
                        "content": [_media_block(item, content), {"type": "text", "text": context}],
                    }
                ],
                output_format=DocumentExtraction,
            )
        _check_refusal(response)
    except (AiUpstreamError, AiRateLimitedError) as exc:
        # Transport/model failures are retryable — recorded on the item, not raised,
        # so the client keeps a stable 200 workflow. AiNotConfiguredError still propagates.
        item.status = IngestionStatus.failed
        item.error = exc.detail
        db.flush()
        return item

    extraction: DocumentExtraction = response.parsed_output
    item.extraction = extraction.model_dump(mode="json")
    item.error = None
    _run_pipeline(db, item, corrections={})
    db.flush()
    return item


def redraft_item(db: Session, item_id: uuid.UUID, corrections: dict) -> IngestionItem:
    """Re-run the deterministic pipeline with human corrections. No AI call."""
    item = get_item(db, item_id)
    if item.status not in (IngestionStatus.needs_info, IngestionStatus.drafted):
        raise ConflictError("Only items awaiting review can be corrected")
    if item.extraction is None:
        raise ConflictError("Item has no extraction to correct")
    previous = (item.proposed_action or {}).get("corrections") or {}
    _run_pipeline(db, item, corrections={**previous, **corrections})
    db.flush()
    return item


def reject_item(db: Session, item_id: uuid.UUID, reason: str, user_id: uuid.UUID) -> IngestionItem:
    item = get_item(db, item_id)
    if item.status in (IngestionStatus.posted, IngestionStatus.rejected):
        raise ConflictError("This item has already been finalized")
    item.status = IngestionStatus.rejected
    item.rejection_reason = reason
    item.reviewed_by = user_id
    item.reviewed_at = datetime.now(UTC)
    db.flush()

    from app.modules.notifications import service as notifications

    notifications.notify(
        db,
        [item.created_by],
        "ingestion_rejected",
        f"{item.original_filename} was rejected",
        reason,
        link="/inbox",
        exclude=user_id,
    )
    return item


# --- Deterministic pipeline: normalize → validate → draft → gate ------------


def _field(section: dict, name: str, corrections: dict) -> tuple[object, float]:
    """Return (value, score) with corrections overriding at confidence 1.0."""
    if name in corrections:
        value = corrections[name]
        return (value if value not in ("", None) else None), 1.0
    raw = section.get(name) or {}
    return raw.get("value"), CONFIDENCE_SCORES.get(raw.get("confidence"), 0.50)


_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y")


def _parse_date(value: object) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _parse_amount(value: object) -> Decimal | None:
    if value is None:
        return None
    text = str(value).replace(",", "").replace("$", "").strip()
    try:
        amount = Decimal(text)
    except InvalidOperation:
        return None
    return amount if amount > 0 else None


def _resolve_project(db: Session, value: object, hint_id: uuid.UUID | None) -> Project | None:
    if value:
        text = str(value).strip()
        project = db.scalar(select(Project).where(func.lower(Project.code) == text.lower()))
        if project is not None:
            return project
        matches = list(db.scalars(select(Project).where(Project.name.ilike(f"%{text}%")).limit(2)))
        if len(matches) == 1:
            return matches[0]
    if hint_id is not None:
        return db.get(Project, hint_id)
    return None


def _resolve_supplier(db: Session, value: object) -> Supplier | None:
    if not value:
        return None
    text = str(value).strip()
    supplier = db.scalar(select(Supplier).where(func.lower(Supplier.name) == text.lower()))
    if supplier is not None:
        return supplier
    matches = list(db.scalars(select(Supplier).where(Supplier.name.ilike(f"%{text}%")).limit(2)))
    return matches[0] if len(matches) == 1 else None


_CATEGORY_ALIASES = {
    "material": ExpenseCategory.materials,
    "materials": ExpenseCategory.materials,
    "transport": ExpenseCategory.transport,
    "travel": ExpenseCategory.transport,
    "fuel": ExpenseCategory.fuel,
    "diesel": ExpenseCategory.fuel,
    "petrol": ExpenseCategory.fuel,
    "accommodation": ExpenseCategory.accommodation,
    "lodging": ExpenseCategory.accommodation,
    "meals": ExpenseCategory.meals,
    "food": ExpenseCategory.meals,
    "tools": ExpenseCategory.tools,
    "equipment": ExpenseCategory.tools,
}


def _resolve_category(value: object) -> ExpenseCategory:
    if not value:
        return ExpenseCategory.other
    text = str(value).strip().lower()
    return _CATEGORY_ALIASES.get(text, ExpenseCategory.other)


def _run_pipeline(db: Session, item: IngestionItem, corrections: dict) -> None:
    ext = item.extraction
    doc_type = ext.get("document_type")
    class_score = CONFIDENCE_SCORES.get(ext.get("classification_confidence"), 0.50)

    if doc_type == "unknown" or doc_type not in {t.value for t in IngestionDocType}:
        item.doc_type = None
        item.status = IngestionStatus.needs_info
        item.proposed_action = {
            "action": None,
            "params": {},
            "display": {"summary": ext.get("summary")},
            "field_confidence": {},
            "missing_fields": [],
            "problems": ["Could not classify this document; reject it or upload a clearer copy"],
            "confidence_score": class_score,
            "gate_passed": False,
            "corrections": corrections,
            "lineage": None,
        }
        return

    item.doc_type = IngestionDocType(doc_type)
    drafters = {
        IngestionDocType.supplier_invoice: _draft_invoice,
        IngestionDocType.expense_receipt: _draft_receipt,
        IngestionDocType.delivery_note: _draft_delivery,
        IngestionDocType.supplier_quote: _draft_quote,
    }
    params, display, scores, missing, problems = drafters[item.doc_type](db, item, corrections)

    all_scores = [class_score, *scores.values()]
    score = round(min(all_scores), 2)
    gate_passed = score >= GATE_THRESHOLD and not missing and not problems
    item.status = IngestionStatus.drafted if gate_passed else IngestionStatus.needs_info
    item.proposed_action = {
        "action": _ACTIONS[item.doc_type],
        "params": params,
        "display": {"summary": ext.get("summary"), **display},
        "field_confidence": {name: value for name, value in scores.items()},
        "missing_fields": missing,
        "problems": problems,
        "confidence_score": score,
        "gate_passed": gate_passed,
        "corrections": corrections,
        "lineage": None,
    }


_ACTIONS = {
    IngestionDocType.supplier_invoice: "create_cost_entry",
    IngestionDocType.expense_receipt: "create_expense_claim",
    IngestionDocType.delivery_note: "receive_po",
    IngestionDocType.supplier_quote: "create_quote",
}


def _draft_invoice(db: Session, item: IngestionItem, corrections: dict):
    section = item.extraction.get("invoice") or {}
    scores: dict[str, float] = {}
    missing: list[str] = []
    problems: list[str] = []

    supplier_name, scores["supplier_name"] = _field(section, "supplier_name", corrections)
    invoice_number, scores["invoice_number"] = _field(section, "invoice_number", corrections)
    raw_date, scores["invoice_date"] = _field(section, "invoice_date", corrections)
    raw_amount, scores["total_amount"] = _field(section, "total_amount", corrections)
    raw_project, scores["project_match"] = _field(section, "project_match", corrections)

    invoice_date = _parse_date(raw_date)
    amount = _parse_amount(raw_amount)
    project = _resolve_project(db, raw_project, item.project_id)

    if not supplier_name:
        missing.append("supplier_name")
    if not invoice_number:
        missing.append("invoice_number")
    if invoice_date is None:
        missing.append("invoice_date")
    if amount is None:
        missing.append("total_amount")
    if project is None:
        missing.append("project_match")
        if raw_project:
            problems.append(f"Project '{raw_project}' not found")

    params = {}
    display = {"supplier_name": supplier_name, "invoice_number": invoice_number}
    if not missing:
        params = {
            "project_id": str(project.id),
            "entry_date": invoice_date.isoformat(),
            "amount": str(amount),
            "description": f"Invoice {invoice_number} — {supplier_name}",
            "reference": str(invoice_number)[:60],
        }
        display |= {
            "project": f"{project.code} — {project.name}",
            "amount": str(amount),
            "entry_date": invoice_date.isoformat(),
        }
    return params, display, scores, missing, problems


def _draft_receipt(db: Session, item: IngestionItem, corrections: dict):
    section = item.extraction.get("receipt") or {}
    scores: dict[str, float] = {}
    missing: list[str] = []
    problems: list[str] = []

    vendor, scores["vendor_name"] = _field(section, "vendor_name", corrections)
    raw_date, scores["receipt_date"] = _field(section, "receipt_date", corrections)
    raw_amount, scores["total_amount"] = _field(section, "total_amount", corrections)
    description, scores["description"] = _field(section, "description", corrections)
    raw_project, scores["project_match"] = _field(section, "project_match", corrections)
    raw_category, _ = _field(section, "category", corrections)  # never blocks: falls back to other

    expense_date = _parse_date(raw_date)
    amount = _parse_amount(raw_amount)
    project = _resolve_project(db, raw_project, item.project_id)
    category = _resolve_category(raw_category)

    if not vendor:
        missing.append("vendor_name")
    if expense_date is None:
        missing.append("receipt_date")
    if amount is None:
        missing.append("total_amount")
    if not description:
        missing.append("description")
    if project is None:
        missing.append("project_match")
        if raw_project:
            problems.append(f"Project '{raw_project}' not found")

    params = {}
    display = {"vendor_name": vendor, "category": category.value}
    if not missing:
        params = {
            "project_id": str(project.id),
            "category": category.value,
            "expense_date": expense_date.isoformat(),
            "amount": str(amount),
            "description": f"{vendor}: {description}",
            "receipt_ref": (str(vendor)[:60]) if vendor else None,
        }
        display |= {
            "project": f"{project.code} — {project.name}",
            "amount": str(amount),
            "expense_date": expense_date.isoformat(),
        }
    return params, display, scores, missing, problems


def _draft_delivery(db: Session, item: IngestionItem, corrections: dict):
    section = item.extraction.get("delivery_note") or {}
    scores: dict[str, float] = {}
    missing: list[str] = []
    problems: list[str] = []

    raw_po, scores["po_match"] = _field(section, "po_match", corrections)
    raw_date, scores["delivery_date"] = _field(section, "delivery_date", corrections)

    delivery_date = _parse_date(raw_date)
    po = None
    if raw_po:
        po = db.scalar(select(PurchaseOrder).where(PurchaseOrder.doc_number == str(raw_po).strip()))
        if po is None:
            problems.append(f"Purchase order '{raw_po}' not found")
        elif po.status != PoStatus.issued:
            problems.append(f"Purchase order {po.doc_number} is {po.status.value}, not issued")
            po = None
    else:
        missing.append("po_match")
    if delivery_date is None:
        missing.append("delivery_date")

    params = {}
    display = {}
    if po is not None and delivery_date is not None:
        params = {"po_id": str(po.id), "received_date": delivery_date.isoformat()}
        display = {
            "po": po.doc_number,
            "supplier": po.supplier.name,
            "received_date": delivery_date.isoformat(),
            "total_amount": str(po.total_amount),
        }
    return params, display, scores, missing, problems


def _draft_quote(db: Session, item: IngestionItem, corrections: dict):
    section = item.extraction.get("quote") or {}
    scores: dict[str, float] = {}
    missing: list[str] = []
    problems: list[str] = []

    raw_rfq, scores["rfq_match"] = _field(section, "rfq_match", corrections)
    raw_supplier, scores["supplier_name"] = _field(section, "supplier_name", corrections)
    raw_valid, _ = _field(section, "valid_until", corrections)
    payment_terms, _ = _field(section, "payment_terms", corrections)
    delivery_terms, _ = _field(section, "delivery_terms", corrections)

    rfq = None
    if raw_rfq:
        rfq = db.scalar(select(Rfq).where(Rfq.doc_number == str(raw_rfq).strip()))
        if rfq is None:
            problems.append(f"RFQ '{raw_rfq}' not found")
        elif rfq.status == RfqStatus.draft:
            problems.append(f"RFQ {rfq.doc_number} has not been issued yet")
            rfq = None
    else:
        missing.append("rfq_match")

    supplier = _resolve_supplier(db, raw_supplier)
    if not raw_supplier:
        missing.append("supplier_name")
    elif supplier is None:
        problems.append(
            f"Supplier '{raw_supplier}' is not registered — create the supplier first"
        )

    if rfq is not None and supplier is not None:
        exists = db.scalar(
            select(Quote).where(Quote.rfq_id == rfq.id, Quote.supplier_id == supplier.id)
        )
        if exists is not None:
            problems.append(f"{supplier.name} already has a quote on {rfq.doc_number}")

    lines = section.get("lines") or []
    if not lines:
        problems.append("No line items were extracted from the quote")
    valid_line_ids = {str(i.id) for i in rfq.items} if rfq is not None else set()
    items = []
    total = Decimal("0")
    for line in lines:
        quantity = _parse_amount(line.get("quantity"))
        unit_price = _parse_amount(line.get("unit_price"))
        if unit_price is None:
            unit_price = Decimal("0") if line.get("unit_price") == 0 else None
        if quantity is None or unit_price is None:
            problems.append(f"Line '{line.get('description')}' has an unreadable quantity or price")
            continue
        rfq_item_id = line.get("rfq_item_id")
        if line.get("match_confidence") == "unmatched" or str(rfq_item_id) not in valid_line_ids:
            rfq_item_id = None
        items.append(
            {
                "rfq_item_id": str(rfq_item_id) if rfq_item_id else None,
                "description": line.get("description") or "",
                "unit": line.get("unit"),
                "quantity": str(quantity),
                "unit_price": str(unit_price),
            }
        )
        total += quantity * unit_price

    params = {}
    display = {"supplier_name": raw_supplier, "line_count": len(items)}
    if rfq is not None and supplier is not None and not problems:
        params = {
            "rfq_id": str(rfq.id),
            "supplier_id": str(supplier.id),
            "valid_until": _parse_date(raw_valid).isoformat() if _parse_date(raw_valid) else None,
            "payment_terms": str(payment_terms)[:255] if payment_terms else None,
            "delivery_terms": str(delivery_terms)[:255] if delivery_terms else None,
            "items": items,
        }
        display |= {"rfq": rfq.doc_number, "supplier": supplier.name, "total": str(total)}
    return params, display, scores, missing, problems
