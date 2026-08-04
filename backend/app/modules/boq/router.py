import uuid

from fastapi import APIRouter, Depends

from app.common.enums import UserRole
from app.core.deps import DbDep, require_roles
from app.modules.boq import service
from app.modules.boq.schemas import (
    BoqItemCreate,
    BoqItemRead,
    BoqItemUpdate,
    BoqSectionCreate,
    BoqSectionRead,
    BoqSectionUpdate,
    BoqSummary,
    BoqTree,
    VariationDecision,
    VariationRegister,
)

router = APIRouter(tags=["boq"])

boq_write = Depends(require_roles(UserRole.project_manager))


@router.get("/projects/{project_id}/boq", response_model=BoqTree)
def get_boq(project_id: uuid.UUID, db: DbDep) -> BoqTree:
    return service.get_boq_tree(db, project_id)


@router.get("/projects/{project_id}/variations", response_model=VariationRegister)
def get_variation_register(project_id: uuid.UUID, db: DbDep) -> VariationRegister:
    return service.variation_register(db, project_id)


@router.post("/boq-items/{item_id}/variation-status", response_model=BoqItemRead)
def decide_variation(
    item_id: uuid.UUID,
    body: VariationDecision,
    db: DbDep,
    _=Depends(require_roles(UserRole.project_manager)),
) -> BoqItemRead:
    return BoqItemRead.model_validate(service.decide_variation(db, item_id, body))


@router.get("/projects/{project_id}/boq/summary", response_model=BoqSummary)
def get_boq_summary(project_id: uuid.UUID, db: DbDep) -> BoqSummary:
    return service.boq_summary(db, project_id)


@router.post(
    "/projects/{project_id}/boq/sections",
    response_model=BoqSectionRead,
    status_code=201,
)
def create_section(
    project_id: uuid.UUID,
    body: BoqSectionCreate,
    db: DbDep,
    user=Depends(require_roles(UserRole.project_manager)),
) -> BoqSectionRead:
    return BoqSectionRead.model_validate(service.create_section(db, project_id, body, user.id))


@router.patch("/boq/sections/{section_id}", response_model=BoqSectionRead, dependencies=[boq_write])
def update_section(section_id: uuid.UUID, body: BoqSectionUpdate, db: DbDep) -> BoqSectionRead:
    return BoqSectionRead.model_validate(service.update_section(db, section_id, body))


@router.delete("/boq/sections/{section_id}", status_code=204, dependencies=[boq_write])
def delete_section(section_id: uuid.UUID, db: DbDep) -> None:
    service.delete_section(db, section_id)


@router.post("/boq/sections/{section_id}/items", response_model=BoqItemRead, status_code=201)
def create_item(
    section_id: uuid.UUID,
    body: BoqItemCreate,
    db: DbDep,
    user=Depends(require_roles(UserRole.project_manager)),
) -> BoqItemRead:
    return BoqItemRead.model_validate(service.create_item(db, section_id, body, user.id))


@router.patch("/boq/items/{item_id}", response_model=BoqItemRead, dependencies=[boq_write])
def update_item(item_id: uuid.UUID, body: BoqItemUpdate, db: DbDep) -> BoqItemRead:
    return BoqItemRead.model_validate(service.update_item(db, item_id, body))


@router.delete("/boq/items/{item_id}", status_code=204, dependencies=[boq_write])
def delete_item(item_id: uuid.UUID, db: DbDep) -> None:
    service.delete_item(db, item_id)
