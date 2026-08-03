import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationFailedError
from app.modules.boq.models import BoqItem
from app.modules.costs.models import CostEntry
from app.modules.costs.schemas import CostEntryCreate, CostEntryUpdate
from app.modules.projects.service import get_project


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


def delete_entry(db: Session, entry_id: uuid.UUID) -> None:
    db.delete(get_entry(db, entry_id))
