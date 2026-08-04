import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.common.doc_numbers import next_doc_number
from app.common.enums import PoStatus, RequisitionStatus, UserRole
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.modules.boq.models import BoqItem
from app.modules.notifications import service as notifications
from app.modules.procurement.models import PoItem, PurchaseOrder, Rfq, RfqItem
from app.modules.procurement.service import get_supplier
from app.modules.projects.service import get_project
from app.modules.requisitions.models import Requisition, RequisitionItem
from app.modules.requisitions.schemas import (
    ConvertToPo,
    RequisitionCreate,
    RequisitionDetail,
    RequisitionRead,
)
from app.modules.users.models import User

ZERO = Decimal("0")

# An open requisition older than this (or needed within it) is flagged urgent
URGENT_AGE_DAYS = 3


def _age_days(requisition: Requisition) -> int:
    return (date.today() - requisition.created_at.date()).days


def _read(db: Session, requisition: Requisition, detail: bool = False) -> RequisitionRead:
    cls = RequisitionDetail if detail else RequisitionRead
    read = cls.model_validate(requisition)
    read.age_days = _age_days(requisition)
    read.is_urgent = requisition.status == RequisitionStatus.open and (
        read.age_days >= URGENT_AGE_DAYS
        or (
            requisition.needed_by is not None
            and (requisition.needed_by - date.today()).days <= URGENT_AGE_DAYS
        )
    )
    read.item_count = len(requisition.items)
    if requisition.project:
        read.project_name = requisition.project.name
        read.project_code = requisition.project.code
    if requisition.created_by:
        requester = db.get(User, requisition.created_by)
        read.requested_by_name = requester.full_name if requester else None
    return read


def requisition_read(db: Session, requisition: Requisition) -> RequisitionRead:
    return _read(db, requisition)


def requisition_detail(db: Session, requisition_id: uuid.UUID) -> RequisitionDetail:
    return _read(db, get_requisition(db, requisition_id), detail=True)


def get_requisition(db: Session, requisition_id: uuid.UUID) -> Requisition:
    requisition = db.get(
        Requisition, requisition_id, options=[joinedload(Requisition.project)]
    )
    if requisition is None:
        raise NotFoundError("Requisition not found")
    return requisition


def list_requisitions(
    db: Session,
    page: int,
    page_size: int,
    project_id: uuid.UUID | None = None,
    status: RequisitionStatus | None = None,
) -> tuple[list[Requisition], int]:
    query = select(Requisition)
    if project_id is not None:
        query = query.where(Requisition.project_id == project_id)
    if status is not None:
        query = query.where(Requisition.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    # Aging queue ordering: open before closed, oldest open first so the most
    # neglected request tops the list.
    is_open = (Requisition.status == RequisitionStatus.open).desc()
    rows = list(
        db.scalars(
            query.options(joinedload(Requisition.project))
            .order_by(
                is_open,
                Requisition.created_at.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return rows, total


def open_requisition_stats(db: Session) -> tuple[int, int]:
    """(open count, oldest open age in days) for the procurement pulse."""
    rows = db.scalars(
        select(Requisition.created_at).where(Requisition.status == RequisitionStatus.open)
    ).all()
    if not rows:
        return 0, 0
    oldest = min(rows)
    return len(rows), (date.today() - oldest.date()).days


def create_requisition(
    db: Session, project_id: uuid.UUID, data: RequisitionCreate, created_by: uuid.UUID
) -> Requisition:
    project = get_project(db, project_id)
    items: list[RequisitionItem] = []
    for order, spec in enumerate(data.items):
        if spec.boq_item_id is not None:
            boq_item = db.get(BoqItem, spec.boq_item_id)
            if boq_item is None or boq_item.project_id != project_id:
                raise ValidationFailedError("BOQ item does not exist in this project")
        items.append(
            RequisitionItem(
                boq_item_id=spec.boq_item_id,
                description=spec.description,
                unit=spec.unit,
                quantity=spec.quantity,
                sort_order=order,
            )
        )
    requisition = Requisition(
        project_id=project_id,
        doc_number=next_doc_number(db, Requisition, "REQ"),
        needed_by=data.needed_by,
        notes=data.notes,
        created_by=created_by,
        items=items,
    )
    db.add(requisition)
    db.flush()

    needed = f", needed by {data.needed_by}" if data.needed_by else ""
    notifications.notify_roles(
        db,
        [UserRole.procurement_officer, UserRole.admin],
        "requisition_created",
        f"{requisition.doc_number} — {project.name} requests {len(items)} "
        f"item{'s' if len(items) != 1 else ''}{needed}",
        data.notes,
        link="/procurement/requisitions",
        exclude=created_by,
    )
    return requisition


def cancel_requisition(db: Session, requisition_id: uuid.UUID) -> Requisition:
    requisition = get_requisition(db, requisition_id)
    if requisition.status != RequisitionStatus.open:
        raise ConflictError("Only open requisitions can be cancelled")
    requisition.status = RequisitionStatus.cancelled
    return requisition


def _mark_actioned(requisition: Requisition, actor_id: uuid.UUID) -> None:
    requisition.status = RequisitionStatus.actioned
    requisition.actioned_at = datetime.now(timezone.utc)
    requisition.actioned_by = actor_id


def _notify_requester(db: Session, requisition: Requisition, what: str, actor_id) -> None:
    notifications.notify(
        db,
        [requisition.created_by],
        "requisition_actioned",
        f"{requisition.doc_number} actioned — {what}",
        link="/procurement/requisitions",
        exclude=actor_id,
    )


def convert_to_rfq(db: Session, requisition_id: uuid.UUID, actor_id: uuid.UUID) -> Rfq:
    """One click: open requisition -> draft RFQ with the same lines."""
    requisition = get_requisition(db, requisition_id)
    if requisition.status != RequisitionStatus.open:
        raise ConflictError("Only open requisitions can be converted")
    project = requisition.project
    rfq = Rfq(
        project_id=requisition.project_id,
        doc_number=next_doc_number(db, Rfq, "RFQ"),
        title=f"Materials for {project.name if project else 'site'} "
        f"({requisition.doc_number})",
        due_date=requisition.needed_by,
        body=requisition.notes,
        created_by=actor_id,
        items=[
            RfqItem(
                boq_item_id=line.boq_item_id,
                description=line.description,
                unit=line.unit[:10],
                quantity=line.quantity,
                sort_order=line.sort_order,
            )
            for line in requisition.items
        ],
    )
    db.add(rfq)
    db.flush()
    requisition.rfq_id = rfq.id
    _mark_actioned(requisition, actor_id)
    _notify_requester(db, requisition, f"RFQ {rfq.doc_number} drafted", actor_id)
    return rfq


def last_known_price(
    db: Session, boq_item_id: uuid.UUID | None, supplier_id: uuid.UUID | None = None
) -> Decimal | None:
    """Most recent non-cancelled PO price for a BOQ item (optionally per supplier)."""
    if boq_item_id is None:
        return None
    query = (
        select(PoItem.unit_price)
        .join(PurchaseOrder, PoItem.po_id == PurchaseOrder.id)
        .where(
            PoItem.boq_item_id == boq_item_id,
            PurchaseOrder.status != PoStatus.cancelled,
        )
        .order_by(PurchaseOrder.order_date.desc(), PurchaseOrder.created_at.desc())
        .limit(1)
    )
    if supplier_id is not None:
        query = query.where(PurchaseOrder.supplier_id == supplier_id)
    return db.scalar(query)


def convert_to_po(
    db: Session, requisition_id: uuid.UUID, data: ConvertToPo, actor_id: uuid.UUID
) -> PurchaseOrder:
    """One click: open requisition -> draft PO for a chosen supplier.

    Line prices default to the last non-cancelled PO price for the same BOQ
    item (any supplier as fallback), else 0 — the draft stays editable and a
    human issues it, per the drafts-only rule.
    """
    requisition = get_requisition(db, requisition_id)
    if requisition.status != RequisitionStatus.open:
        raise ConflictError("Only open requisitions can be converted")
    supplier = get_supplier(db, data.supplier_id)

    total = ZERO
    po_items = []
    for line in requisition.items:
        price = (
            last_known_price(db, line.boq_item_id, supplier.id)
            or last_known_price(db, line.boq_item_id)
            or ZERO
        ).quantize(Decimal("0.01"))
        po_items.append(
            PoItem(
                boq_item_id=line.boq_item_id,
                description=line.description,
                unit=line.unit,
                quantity=line.quantity,
                unit_price=price,
            )
        )
        total += line.quantity * price

    po = PurchaseOrder(
        project_id=requisition.project_id,
        supplier_id=supplier.id,
        doc_number=next_doc_number(db, PurchaseOrder, "PO"),
        expected_delivery=data.expected_delivery or requisition.needed_by,
        notes=data.notes or requisition.notes,
        total_amount=total.quantize(Decimal("0.01")),
        created_by=actor_id,
        items=po_items,
    )
    db.add(po)
    db.flush()
    requisition.po_id = po.id
    _mark_actioned(requisition, actor_id)
    _notify_requester(db, requisition, f"PO {po.doc_number} drafted", actor_id)
    return po
