import uuid
from datetime import date

from fastapi import APIRouter, Depends

from app.common.enums import UserRole
from app.common.pagination import PageParamsDep
from app.common.schemas import Page
from app.core.deps import CurrentUser, DbDep, require_roles
from app.modules.boq.models import BoqItem
from app.modules.costs import service
from app.modules.costs.schemas import CostEntryCreate, CostEntryRead, CostEntryUpdate

router = APIRouter(tags=["costs"])

cost_write = Depends(require_roles(UserRole.project_manager, UserRole.site_manager))


def _to_read(db, entry) -> CostEntryRead:
    read = CostEntryRead.model_validate(entry)
    if entry.boq_item_id:
        item = db.get(BoqItem, entry.boq_item_id)
        if item:
            read.boq_item_code = item.item_code
            read.boq_item_description = item.description
    return read


@router.get("/projects/{project_id}/cost-entries", response_model=Page[CostEntryRead])
def list_cost_entries(
    project_id: uuid.UUID,
    db: DbDep,
    params: PageParamsDep,
    boq_item_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Page[CostEntryRead]:
    entries, total = service.list_entries(
        db, project_id, params.page, params.page_size, boq_item_id, date_from, date_to
    )
    return Page(
        items=[_to_read(db, e) for e in entries],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.post("/projects/{project_id}/cost-entries", response_model=CostEntryRead, status_code=201)
def create_cost_entry(
    project_id: uuid.UUID,
    body: CostEntryCreate,
    db: DbDep,
    user=Depends(require_roles(UserRole.project_manager, UserRole.site_manager)),
) -> CostEntryRead:
    return _to_read(db, service.create_entry(db, project_id, body, user.id))


@router.patch("/cost-entries/{entry_id}", response_model=CostEntryRead, dependencies=[cost_write])
def update_cost_entry(entry_id: uuid.UUID, body: CostEntryUpdate, db: DbDep) -> CostEntryRead:
    return _to_read(db, service.update_entry(db, entry_id, body))


@router.delete("/cost-entries/{entry_id}", status_code=204, dependencies=[cost_write])
def delete_cost_entry(entry_id: uuid.UUID, db: DbDep, user: CurrentUser) -> None:
    service.delete_entry(db, entry_id, user)
