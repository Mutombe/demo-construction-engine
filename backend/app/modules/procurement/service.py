import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.common.doc_numbers import next_doc_number
from app.common.enums import CostSource, PoStatus, QuoteStatus, RfqStatus
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.modules.boq.models import BoqItem
from app.modules.costs.models import CostEntry
from app.modules.procurement.models import (
    PoItem,
    PurchaseOrder,
    Quote,
    QuoteItem,
    Rfq,
    RfqItem,
    Supplier,
)
from app.modules.procurement.schemas import (
    PoCreate,
    PoReceive,
    PoUpdate,
    QuoteCreate,
    QuoteItemRead,
    QuoteRead,
    QuoteUpdate,
    RfqCreate,
    RfqDetail,
    RfqItemCreate,
    RfqRead,
    RfqUpdate,
    SupplierCreate,
    SupplierUpdate,
)
from app.modules.projects.service import get_project

ZERO = Decimal("0")


# --- Doc numbers ------------------------------------------------------------


# --- Suppliers --------------------------------------------------------------


def list_suppliers(
    db: Session,
    page: int,
    page_size: int,
    search: str | None = None,
    active_only: bool = False,
) -> tuple[list[Supplier], int]:
    query = select(Supplier)
    if search:
        query = query.where(
            Supplier.name.ilike(f"%{search}%") | Supplier.categories.ilike(f"%{search}%")
        )
    if active_only:
        query = query.where(Supplier.is_active.is_(True))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    suppliers = list(
        db.scalars(query.order_by(Supplier.name).offset((page - 1) * page_size).limit(page_size))
    )
    return suppliers, total


def get_supplier(db: Session, supplier_id: uuid.UUID) -> Supplier:
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise NotFoundError("Supplier not found")
    return supplier


def create_supplier(db: Session, data: SupplierCreate, created_by: uuid.UUID) -> Supplier:
    if db.scalar(select(Supplier).where(Supplier.name == data.name)):
        raise ConflictError("A supplier with this name already exists")
    supplier = Supplier(**data.model_dump(), created_by=created_by)
    db.add(supplier)
    db.flush()
    return supplier


def update_supplier(db: Session, supplier_id: uuid.UUID, data: SupplierUpdate) -> Supplier:
    supplier = get_supplier(db, supplier_id)
    updates = data.model_dump(exclude_unset=True)
    if (
        "name" in updates
        and updates["name"] != supplier.name
        and db.scalar(select(Supplier).where(Supplier.name == updates["name"]))
    ):
        raise ConflictError("A supplier with this name already exists")
    for field, value in updates.items():
        setattr(supplier, field, value)
    return supplier


# --- RFQs -------------------------------------------------------------------


def _rfq_counts(db: Session, rfq_ids: list[uuid.UUID]) -> tuple[dict, dict]:
    if not rfq_ids:
        return {}, {}
    item_counts = dict(
        db.execute(
            select(RfqItem.rfq_id, func.count())
            .where(RfqItem.rfq_id.in_(rfq_ids))
            .group_by(RfqItem.rfq_id)
        ).all()
    )
    quote_counts = dict(
        db.execute(
            select(Quote.rfq_id, func.count())
            .where(Quote.rfq_id.in_(rfq_ids))
            .group_by(Quote.rfq_id)
        ).all()
    )
    return item_counts, quote_counts


def list_rfqs(
    db: Session, project_id: uuid.UUID, page: int, page_size: int
) -> tuple[list[RfqRead], int]:
    get_project(db, project_id)
    query = select(Rfq).where(Rfq.project_id == project_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rfqs = list(
        db.scalars(
            query.order_by(Rfq.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
    )
    item_counts, quote_counts = _rfq_counts(db, [r.id for r in rfqs])
    reads = []
    for r in rfqs:
        read = RfqRead.model_validate(r)
        read.item_count = item_counts.get(r.id, 0)
        read.quote_count = quote_counts.get(r.id, 0)
        reads.append(read)
    return reads, total


def get_rfq(db: Session, rfq_id: uuid.UUID) -> Rfq:
    rfq = db.get(Rfq, rfq_id, options=[joinedload(Rfq.project)])
    if rfq is None:
        raise NotFoundError("RFQ not found")
    return rfq


def rfq_detail(db: Session, rfq_id: uuid.UUID) -> RfqDetail:
    rfq = get_rfq(db, rfq_id)
    item_counts, quote_counts = _rfq_counts(db, [rfq.id])
    detail = RfqDetail.model_validate(rfq)
    detail.item_count = item_counts.get(rfq.id, 0)
    detail.quote_count = quote_counts.get(rfq.id, 0)
    detail.project_name = rfq.project.name if rfq.project else None
    detail.project_code = rfq.project.code if rfq.project else None
    return detail


def _snapshot_items(
    db: Session, project_id: uuid.UUID, items: list[RfqItemCreate]
) -> list[RfqItem]:
    seen: set[uuid.UUID] = set()
    result = []
    for i, spec in enumerate(items):
        if spec.boq_item_id in seen:
            raise ValidationFailedError("Duplicate BOQ item in RFQ lines")
        seen.add(spec.boq_item_id)
        boq_item = db.get(BoqItem, spec.boq_item_id)
        if boq_item is None or boq_item.project_id != project_id:
            raise ValidationFailedError("BOQ item does not exist in this project")
        result.append(
            RfqItem(
                boq_item_id=boq_item.id,
                description=boq_item.description,
                unit=boq_item.unit,
                quantity=spec.quantity if spec.quantity is not None else boq_item.quantity,
                sort_order=i,
            )
        )
    return result


def create_rfq(db: Session, project_id: uuid.UUID, data: RfqCreate, created_by: uuid.UUID) -> Rfq:
    get_project(db, project_id)
    rfq = Rfq(
        project_id=project_id,
        doc_number=next_doc_number(db, Rfq, "RFQ"),
        title=data.title,
        body=data.body,
        due_date=data.due_date,
        ai_generated=data.ai_generated,
        created_by=created_by,
        items=_snapshot_items(db, project_id, data.items),
    )
    db.add(rfq)
    db.flush()
    return rfq


def _require_draft(rfq: Rfq) -> None:
    if rfq.status != RfqStatus.draft:
        raise ConflictError("RFQ can only be modified while in draft")


def update_rfq(db: Session, rfq_id: uuid.UUID, data: RfqUpdate) -> Rfq:
    rfq = get_rfq(db, rfq_id)
    _require_draft(rfq)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(rfq, field, value)
    return rfq


def replace_rfq_items(db: Session, rfq_id: uuid.UUID, items: list[RfqItemCreate]) -> Rfq:
    rfq = get_rfq(db, rfq_id)
    _require_draft(rfq)
    rfq.items = _snapshot_items(db, rfq.project_id, items)
    db.flush()
    return rfq


def issue_rfq(db: Session, rfq_id: uuid.UUID) -> Rfq:
    rfq = get_rfq(db, rfq_id)
    _require_draft(rfq)
    rfq.status = RfqStatus.issued
    return rfq


def delete_rfq(db: Session, rfq_id: uuid.UUID) -> None:
    rfq = get_rfq(db, rfq_id)
    _require_draft(rfq)
    db.delete(rfq)


# --- Quotes -----------------------------------------------------------------


def _normalize_unit(unit: str | None) -> str:
    return (unit or "").strip().lower()


def quote_read(db: Session, quote: Quote) -> QuoteRead:
    rfq_items = {item.id: item for item in quote.rfq.items}
    item_reads = []
    matched = 0
    for item in quote.items:
        read = QuoteItemRead.model_validate(item)
        rfq_item = rfq_items.get(item.rfq_item_id) if item.rfq_item_id else None
        if rfq_item is not None:
            matched += 1
            read.unit_mismatch = _normalize_unit(item.unit) != _normalize_unit(rfq_item.unit)
            read.quantity_mismatch = item.quantity != rfq_item.quantity
        item_reads.append(read)
    read = QuoteRead.model_validate(quote)
    read.supplier_name = quote.supplier.name if quote.supplier else None
    read.items = item_reads
    read.coverage_pct = round(matched / len(rfq_items) * 100, 1) if rfq_items else 100.0
    return read


def list_quotes(db: Session, rfq_id: uuid.UUID) -> list[QuoteRead]:
    get_rfq(db, rfq_id)
    quotes = (
        db.scalars(
            select(Quote)
            .options(
                joinedload(Quote.supplier),
                joinedload(Quote.items),
                joinedload(Quote.rfq).joinedload(Rfq.items),
            )
            .where(Quote.rfq_id == rfq_id)
            .order_by(Quote.created_at)
        )
        .unique()
        .all()
    )
    return [quote_read(db, q) for q in quotes]


def get_quote(db: Session, quote_id: uuid.UUID) -> Quote:
    quote = db.get(
        Quote,
        quote_id,
        options=[
            joinedload(Quote.supplier),
            joinedload(Quote.items),
            joinedload(Quote.rfq).joinedload(Rfq.items),
        ],
    )
    if quote is None:
        raise NotFoundError("Quote not found")
    return quote


def create_quote(db: Session, rfq_id: uuid.UUID, data: QuoteCreate, created_by: uuid.UUID) -> Quote:
    rfq = get_rfq(db, rfq_id)
    if rfq.status == RfqStatus.draft:
        raise ConflictError("Issue the RFQ before recording quotes")
    supplier = get_supplier(db, data.supplier_id)
    if db.scalar(select(Quote).where(Quote.rfq_id == rfq_id, Quote.supplier_id == supplier.id)):
        raise ConflictError("This supplier already has a quote on this RFQ")

    rfq_item_ids = {item.id for item in rfq.items}
    seen_rfq_items: set[uuid.UUID] = set()
    total = ZERO
    quote_items = []
    for spec in data.items:
        if spec.rfq_item_id is not None:
            if spec.rfq_item_id not in rfq_item_ids:
                raise ValidationFailedError("Quote line references a line not on this RFQ")
            if spec.rfq_item_id in seen_rfq_items:
                raise ValidationFailedError("Duplicate RFQ line in quote")
            seen_rfq_items.add(spec.rfq_item_id)
        total += spec.quantity * spec.unit_price
        quote_items.append(
            QuoteItem(
                rfq_item_id=spec.rfq_item_id,
                description=spec.description,
                unit=spec.unit,
                quantity=spec.quantity,
                unit_price=spec.unit_price,
            )
        )

    quote = Quote(
        rfq_id=rfq_id,
        supplier_id=supplier.id,
        received_date=data.received_date or date.today(),
        valid_until=data.valid_until,
        payment_terms=data.payment_terms,
        delivery_terms=data.delivery_terms,
        notes=data.notes,
        raw_text=data.raw_text,
        ai_extracted=data.ai_extracted,
        total_amount=total.quantize(Decimal("0.01")),
        created_by=created_by,
        items=quote_items,
    )
    db.add(quote)
    db.flush()
    return get_quote(db, quote.id)


def update_quote(db: Session, quote_id: uuid.UUID, data: QuoteUpdate) -> Quote:
    quote = get_quote(db, quote_id)
    if quote.status != QuoteStatus.received:
        raise ConflictError("Only received quotes can be edited")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(quote, field, value)
    return quote


def delete_quote(db: Session, quote_id: uuid.UUID) -> None:
    quote = get_quote(db, quote_id)
    if quote.status != QuoteStatus.received:
        raise ConflictError("Accepted or rejected quotes cannot be deleted")
    db.delete(quote)


def accept_quote(db: Session, quote_id: uuid.UUID) -> Quote:
    quote = get_quote(db, quote_id)
    rfq = quote.rfq
    if rfq.status != RfqStatus.issued:
        raise ConflictError("Quotes can only be accepted on an issued RFQ")
    siblings = db.scalars(select(Quote).where(Quote.rfq_id == rfq.id)).all()
    for sibling in siblings:
        sibling.status = QuoteStatus.accepted if sibling.id == quote.id else QuoteStatus.rejected
    rfq.status = RfqStatus.closed
    db.flush()
    return get_quote(db, quote.id)


# --- Purchase orders --------------------------------------------------------


def list_pos(
    db: Session, project_id: uuid.UUID, page: int, page_size: int
) -> tuple[list[PurchaseOrder], int]:
    get_project(db, project_id)
    query = (
        select(PurchaseOrder)
        .options(joinedload(PurchaseOrder.supplier))
        .where(PurchaseOrder.project_id == project_id)
    )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    pos = list(
        db.scalars(
            query.order_by(PurchaseOrder.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return pos, total


def get_po(db: Session, po_id: uuid.UUID) -> PurchaseOrder:
    po = db.get(
        PurchaseOrder,
        po_id,
        options=[
            joinedload(PurchaseOrder.supplier),
            joinedload(PurchaseOrder.items),
            joinedload(PurchaseOrder.project),
        ],
    )
    if po is None:
        raise NotFoundError("Purchase order not found")
    return po


def create_po(
    db: Session, project_id: uuid.UUID, data: PoCreate, created_by: uuid.UUID
) -> PurchaseOrder:
    get_project(db, project_id)

    if data.quote_id is not None:
        quote = get_quote(db, data.quote_id)
        if quote.rfq.project_id != project_id:
            raise ValidationFailedError("Quote belongs to another project")
        supplier_id = quote.supplier_id
        # Deterministic mapping: quote line -> PO line, BOQ id threaded via RFQ line
        rfq_items = {item.id: item for item in quote.rfq.items}
        po_items = []
        total = ZERO
        for qi in quote.items:
            rfq_item = rfq_items.get(qi.rfq_item_id) if qi.rfq_item_id else None
            po_items.append(
                PoItem(
                    boq_item_id=rfq_item.boq_item_id if rfq_item else None,
                    description=qi.description,
                    unit=qi.unit,
                    quantity=qi.quantity,
                    unit_price=qi.unit_price,
                )
            )
            total += qi.quantity * qi.unit_price
    else:
        if data.supplier_id is None:
            raise ValidationFailedError("supplier_id is required when no quote is given")
        if not data.items:
            raise ValidationFailedError("items are required when no quote is given")
        get_supplier(db, data.supplier_id)
        supplier_id = data.supplier_id
        po_items = []
        total = ZERO
        for spec in data.items:
            if spec.boq_item_id is not None:
                boq_item = db.get(BoqItem, spec.boq_item_id)
                if boq_item is None or boq_item.project_id != project_id:
                    raise ValidationFailedError("BOQ item does not exist in this project")
            po_items.append(
                PoItem(
                    boq_item_id=spec.boq_item_id,
                    description=spec.description,
                    unit=spec.unit,
                    quantity=spec.quantity,
                    unit_price=spec.unit_price,
                )
            )
            total += spec.quantity * spec.unit_price

    po = PurchaseOrder(
        project_id=project_id,
        supplier_id=supplier_id,
        quote_id=data.quote_id,
        doc_number=next_doc_number(db, PurchaseOrder, "PO"),
        expected_delivery=data.expected_delivery,
        terms=data.terms,
        notes=data.notes,
        ai_generated=data.ai_generated,
        total_amount=total.quantize(Decimal("0.01")),
        created_by=created_by,
        items=po_items,
    )
    db.add(po)
    db.flush()
    return get_po(db, po.id)


def update_po(db: Session, po_id: uuid.UUID, data: PoUpdate) -> PurchaseOrder:
    po = get_po(db, po_id)
    if po.status != PoStatus.draft:
        raise ConflictError("Only draft purchase orders can be edited")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(po, field, value)
    return po


def issue_po(db: Session, po_id: uuid.UUID) -> PurchaseOrder:
    po = get_po(db, po_id)
    if po.status != PoStatus.draft:
        raise ConflictError("Only draft purchase orders can be issued")
    po.status = PoStatus.issued
    return po


def receive_po(db: Session, po_id: uuid.UUID, body: PoReceive, user_id: uuid.UUID) -> PurchaseOrder:
    """One-shot full receipt.

    destination=project: posts one cost entry per PO line against the budget.
    destination=store: books each line into the store via inventory goods_in
    (WAC + GRN movement) with NO cost entries — cost hits the project only when
    stock is later issued.
    """
    from app.common.enums import PoDestination

    po = get_po(db, po_id)
    if po.status != PoStatus.issued:
        raise ConflictError("Only issued purchase orders can be received")
    when = body.received_date or date.today()

    if body.destination == PoDestination.store:
        _receive_to_store(db, po, body, when, user_id)
    else:
        for item in po.items:
            db.add(
                CostEntry(
                    project_id=po.project_id,
                    boq_item_id=item.boq_item_id,
                    entry_date=when,
                    description=f"PO {po.doc_number}: {item.description}",
                    amount=item.amount,
                    quantity=item.quantity,
                    source=CostSource.purchase_order,
                    reference=po.doc_number,
                    created_by=user_id,
                )
            )

    po.status = PoStatus.received
    po.received_date = when
    po.received_to = body.destination
    db.flush()
    return po


def _receive_to_store(db: Session, po: PurchaseOrder, body, when: date, user_id) -> None:
    from app.modules.inventory.schemas import GoodsInRequest
    from app.modules.inventory.service import create_item as inv_create_item
    from app.modules.inventory.service import get_item as inv_get_item
    from app.modules.inventory.service import goods_in as inv_goods_in

    mappings = body.store_lines or []
    po_item_ids = {item.id for item in po.items}
    mapped_ids = [m.po_item_id for m in mappings]
    if set(mapped_ids) != po_item_ids or len(mapped_ids) != len(po_item_ids):
        raise ValidationFailedError(
            "Every purchase order line must be mapped to a stock item exactly once"
        )
    for mapping in mappings:
        if (mapping.stock_item_id is None) == (mapping.new_item is None):
            raise ValidationFailedError(
                "Each line mapping needs exactly one of stock_item_id or new_item"
            )

    po_items = {item.id: item for item in po.items}
    for mapping in mappings:
        line = po_items[mapping.po_item_id]
        if mapping.stock_item_id is not None:
            stock_item = inv_get_item(db, mapping.stock_item_id)
        else:
            stock_item = inv_create_item(db, mapping.new_item, user_id)
        inv_goods_in(
            db,
            stock_item.id,
            GoodsInRequest(
                quantity=line.quantity,
                unit_cost=line.unit_price,
                movement_date=when,
                reference=po.doc_number,
                notes=f"Receipt of {po.doc_number}: {line.description}",
            ),
            user_id,
        )


def cancel_po(db: Session, po_id: uuid.UUID) -> PurchaseOrder:
    po = get_po(db, po_id)
    if po.status not in (PoStatus.draft, PoStatus.issued):
        raise ConflictError("Received purchase orders cannot be cancelled")
    po.status = PoStatus.cancelled
    return po
