"""Approval adapters: the ONLY code path that turns an AI draft into real records.

Each adapter re-parses the JSON-safe params and calls the same domain service a
human would have used, so every guard (duplicate quotes, PO state machine,
expense self-approval) still applies.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.common.enums import (
    CostSource,
    ExpenseCategory,
    IngestionDocType,
    IngestionStatus,
    UserRole,
)
from app.core.exceptions import ConflictError, ForbiddenError
from app.modules.costs.models import CostEntry
from app.modules.expenses import service as expenses_service
from app.modules.expenses.schemas import ExpenseClaimCreate
from app.modules.ingestion.models import IngestionItem
from app.modules.ingestion.service import get_item
from app.modules.procurement import service as procurement_service
from app.modules.procurement.schemas import PoReceive, QuoteCreate, QuoteItemCreate
from app.modules.users.models import User

# Receipts only file a *pending* claim (still needs a PM approval), so site managers
# may post them; the other three create live records immediately.
APPROVAL_ROLES: dict[IngestionDocType, tuple[UserRole, ...]] = {
    IngestionDocType.supplier_invoice: (UserRole.project_manager, UserRole.procurement_officer),
    IngestionDocType.expense_receipt: (
        UserRole.project_manager,
        UserRole.procurement_officer,
        UserRole.site_manager,
    ),
    IngestionDocType.delivery_note: (UserRole.project_manager, UserRole.procurement_officer),
    IngestionDocType.supplier_quote: (UserRole.project_manager, UserRole.procurement_officer),
}


def approve_item(db: Session, item_id: uuid.UUID, approver: User) -> IngestionItem:
    item = get_item(db, item_id)
    if item.status != IngestionStatus.drafted:
        raise ConflictError("Only drafted items can be approved")
    action = item.proposed_action or {}
    if not action.get("gate_passed"):
        raise ConflictError("This draft did not pass the confidence gate")
    if approver.role != UserRole.admin and approver.role not in APPROVAL_ROLES[item.doc_type]:
        raise ForbiddenError(f"Your role cannot approve {item.doc_type.value} documents")

    lineage = _POSTERS[item.doc_type](db, item, approver)
    item.proposed_action = {
        **action,
        "lineage": {
            **lineage,
            "approved_by": str(approver.id),
            "approved_at": datetime.now(UTC).isoformat(),
            "source_file": item.original_filename,
            "confidence_score": action.get("confidence_score"),
        },
    }
    item.status = IngestionStatus.posted
    item.reviewed_by = approver.id
    item.reviewed_at = datetime.now(UTC)
    db.flush()
    return item


def _post_invoice(db: Session, item: IngestionItem, approver: User) -> dict:
    params = item.proposed_action["params"]
    entry = CostEntry(
        project_id=uuid.UUID(params["project_id"]),
        entry_date=date.fromisoformat(params["entry_date"]),
        description=params["description"],
        amount=Decimal(params["amount"]),
        source=CostSource.invoice,
        reference=params["reference"],
        created_by=approver.id,
    )
    db.add(entry)
    db.flush()
    return {
        "posted_type": "cost_entry",
        "posted_id": str(entry.id),
        "reference": params["reference"],
    }


def _post_receipt(db: Session, item: IngestionItem, approver: User) -> dict:
    params = item.proposed_action["params"]
    claim = expenses_service.create_claim(
        db,
        uuid.UUID(params["project_id"]),
        ExpenseClaimCreate(
            category=ExpenseCategory(params["category"]),
            expense_date=date.fromisoformat(params["expense_date"]),
            amount=Decimal(params["amount"]),
            description=params["description"],
            receipt_ref=params.get("receipt_ref"),
        ),
        # The uploader is the claimant: the claim lands pending and the normal
        # approval flow (incl. the self-approval guard) still applies.
        created_by=item.created_by,
    )
    return {
        "posted_type": "expense_claim",
        "posted_id": str(claim.id),
        "reference": claim.doc_number,
    }


def _post_delivery(db: Session, item: IngestionItem, approver: User) -> dict:
    params = item.proposed_action["params"]
    po = procurement_service.receive_po(
        db,
        uuid.UUID(params["po_id"]),
        PoReceive(received_date=date.fromisoformat(params["received_date"])),
        user_id=approver.id,
    )
    return {"posted_type": "purchase_order", "posted_id": str(po.id), "reference": po.doc_number}


def _post_quote(db: Session, item: IngestionItem, approver: User) -> dict:
    params = item.proposed_action["params"]
    quote = procurement_service.create_quote(
        db,
        uuid.UUID(params["rfq_id"]),
        QuoteCreate(
            supplier_id=uuid.UUID(params["supplier_id"]),
            valid_until=(
                date.fromisoformat(params["valid_until"]) if params.get("valid_until") else None
            ),
            payment_terms=params.get("payment_terms"),
            delivery_terms=params.get("delivery_terms"),
            ai_extracted=True,
            items=[
                QuoteItemCreate(
                    rfq_item_id=uuid.UUID(line["rfq_item_id"]) if line.get("rfq_item_id") else None,
                    description=line["description"],
                    unit=line.get("unit"),
                    quantity=Decimal(line["quantity"]),
                    unit_price=Decimal(line["unit_price"]),
                )
                for line in params["items"]
            ],
        ),
        created_by=approver.id,
    )
    return {"posted_type": "quote", "posted_id": str(quote.id), "reference": quote.rfq.doc_number}


_POSTERS = {
    IngestionDocType.supplier_invoice: _post_invoice,
    IngestionDocType.expense_receipt: _post_receipt,
    IngestionDocType.delivery_note: _post_delivery,
    IngestionDocType.supplier_quote: _post_quote,
}
