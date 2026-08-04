import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import PoStatus
from app.core.exceptions import NotFoundError, ValidationFailedError
from app.modules.boq.models import BoqItem
from app.modules.costs.models import CostEntry
from app.modules.costs.schemas import CostEntryCreate, CostEntryUpdate
from app.modules.projects.service import get_project
from app.modules.admin import trash


def list_entries(
    db: Session,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    boq_item_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> tuple[list[CostEntry], int]:
    get_project(db, project_id)
    query = select(CostEntry).where(CostEntry.project_id == project_id)
    if boq_item_id is not None:
        query = query.where(CostEntry.boq_item_id == boq_item_id)
    if date_from is not None:
        query = query.where(CostEntry.entry_date >= date_from)
    if date_to is not None:
        query = query.where(CostEntry.entry_date <= date_to)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    entries = list(
        db.scalars(
            query.order_by(CostEntry.entry_date.desc(), CostEntry.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return entries, total


def get_entry(db: Session, entry_id: uuid.UUID) -> CostEntry:
    entry = db.get(CostEntry, entry_id)
    if entry is None:
        raise NotFoundError("Cost entry not found")
    return entry


def _validate_boq_item(db: Session, project_id: uuid.UUID, boq_item_id: uuid.UUID) -> None:
    item = db.get(BoqItem, boq_item_id)
    if item is None or item.project_id != project_id:
        raise ValidationFailedError("BOQ item does not exist in this project")


def create_entry(
    db: Session, project_id: uuid.UUID, data: CostEntryCreate, created_by: uuid.UUID
) -> CostEntry:
    get_project(db, project_id)
    if data.boq_item_id is not None:
        _validate_boq_item(db, project_id, data.boq_item_id)
    entry = CostEntry(**data.model_dump(), project_id=project_id, created_by=created_by)
    db.add(entry)
    db.flush()
    return entry


def update_entry(db: Session, entry_id: uuid.UUID, data: CostEntryUpdate) -> CostEntry:
    entry = get_entry(db, entry_id)
    updates = data.model_dump(exclude_unset=True)
    if updates.get("boq_item_id") is not None:
        _validate_boq_item(db, entry.project_id, updates["boq_item_id"])
    for field, value in updates.items():
        setattr(entry, field, value)
    return entry


def delete_entry(db: Session, entry_id: uuid.UUID, user=None) -> None:
    entry = get_entry(db, entry_id)
    trash.archive(
        db,
        entry,
        entity_type="cost_entry",
        label=f"{entry.description} ({entry.amount})",
        user=user,
    )
    db.delete(entry)


# --- Committed costs ---------------------------------------------------------
#
# An ISSUED purchase order is money the company has promised but not yet spent.
# Drafts are not commitments (nothing has been sent to the supplier) and
# received orders have already become cost entries, so counting either would
# double-count. Budget views that show only actuals report a project as
# under budget while its commitments have already overrun it.


def committed_by_boq_item(db: Session, project_id: uuid.UUID) -> dict[uuid.UUID, Decimal]:
    from app.modules.procurement.models import PoItem, PurchaseOrder

    rows = db.execute(
        select(PoItem.boq_item_id, func.coalesce(func.sum(PoItem.amount), 0))
        .join(PurchaseOrder, PoItem.po_id == PurchaseOrder.id)
        .where(
            PurchaseOrder.status == PoStatus.issued,
            PurchaseOrder.project_id == project_id,
            PoItem.boq_item_id.is_not(None),
        )
        .group_by(PoItem.boq_item_id)
    ).all()
    return {item_id: total for item_id, total in rows}


def committed_total(db: Session, project_id: uuid.UUID) -> Decimal:
    from app.modules.procurement.models import PoItem, PurchaseOrder

    return db.scalar(
        select(func.coalesce(func.sum(PoItem.amount), 0))
        .join(PurchaseOrder, PoItem.po_id == PurchaseOrder.id)
        .where(
            PurchaseOrder.status == PoStatus.issued,
            PurchaseOrder.project_id == project_id,
        )
    ) or Decimal("0")


def committed_by_project(db: Session) -> dict[uuid.UUID, Decimal]:
    """Portfolio-wide commitments, for the dashboard."""
    from app.modules.procurement.models import PoItem, PurchaseOrder

    rows = db.execute(
        select(PurchaseOrder.project_id, func.coalesce(func.sum(PoItem.amount), 0))
        .join(PoItem, PoItem.po_id == PurchaseOrder.id)
        .where(PurchaseOrder.status == PoStatus.issued)
        .group_by(PurchaseOrder.project_id)
    ).all()
    return {project_id: total for project_id, total in rows}
