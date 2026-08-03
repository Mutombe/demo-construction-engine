import uuid

from fastapi import APIRouter, Depends

from app.common.enums import ProjectStatus, UserRole
from app.common.pagination import PageParamsDep
from app.common.schemas import Page
from app.core.deps import DbDep, require_roles
from app.modules.projects import service
from app.modules.projects.schemas import (
    PhaseCreate,
    PhaseRead,
    PhaseReorder,
    PhaseUpdate,
    ProjectCreate,
    ProjectListItem,
    ProjectMapPin,
    ProjectRead,
    ProjectSummary,
    ProjectUpdate,
)

router = APIRouter(tags=["projects"])

pm_write = Depends(require_roles(UserRole.project_manager))


def _to_list_item(p) -> ProjectListItem:
    item = ProjectListItem.model_validate(p)
    item.client_name = p.client.name if p.client else None
    item.project_manager_name = p.project_manager.full_name if p.project_manager else None
    return item


@router.get("/projects", response_model=Page[ProjectListItem])
def list_projects(
    db: DbDep,
    params: PageParamsDep,
    status: ProjectStatus | None = None,
    client_id: uuid.UUID | None = None,
    project_manager_id: uuid.UUID | None = None,
    search: str | None = None,
) -> Page[ProjectListItem]:
    projects, total = service.list_projects(
        db, params.page, params.page_size, status, client_id, project_manager_id, search
    )
    return Page(
        items=[_to_list_item(p) for p in projects],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


# NOTE: declared before /projects/{project_id} so "map" never hits the UUID route
@router.get("/projects/map", response_model=list[ProjectMapPin])
def get_project_map_pins(db: DbDep) -> list[ProjectMapPin]:
    return service.map_pins(db)


@router.post("/projects", response_model=ProjectRead, status_code=201)
def create_project(
    body: ProjectCreate, db: DbDep, user=Depends(require_roles(UserRole.project_manager))
) -> ProjectRead:
    return ProjectRead.model_validate(service.create_project(db, body, user.id))


@router.get("/projects/{project_id}", response_model=ProjectListItem)
def get_project(project_id: uuid.UUID, db: DbDep) -> ProjectListItem:
    return _to_list_item(service.get_project(db, project_id))


@router.patch("/projects/{project_id}", response_model=ProjectRead, dependencies=[pm_write])
def update_project(project_id: uuid.UUID, body: ProjectUpdate, db: DbDep) -> ProjectRead:
    return ProjectRead.model_validate(service.update_project(db, project_id, body))


@router.delete(
    "/projects/{project_id}",
    status_code=204,
    dependencies=[Depends(require_roles())],  # admin only
)
def delete_project(project_id: uuid.UUID, db: DbDep) -> None:
    service.delete_project(db, project_id)


@router.get("/projects/{project_id}/summary", response_model=ProjectSummary)
def get_project_summary(project_id: uuid.UUID, db: DbDep) -> ProjectSummary:
    return service.project_summary(db, project_id)


# --- Phases ----------------------------------------------------------------


@router.get("/projects/{project_id}/phases", response_model=list[PhaseRead])
def list_phases(project_id: uuid.UUID, db: DbDep) -> list[PhaseRead]:
    return [PhaseRead.model_validate(p) for p in service.list_phases(db, project_id)]


@router.post("/projects/{project_id}/phases", response_model=PhaseRead, status_code=201)
def create_phase(
    project_id: uuid.UUID,
    body: PhaseCreate,
    db: DbDep,
    user=Depends(require_roles(UserRole.project_manager)),
) -> PhaseRead:
    return PhaseRead.model_validate(service.create_phase(db, project_id, body, user.id))


@router.post(
    "/projects/{project_id}/phases/reorder",
    response_model=list[PhaseRead],
    dependencies=[pm_write],
)
def reorder_phases(project_id: uuid.UUID, body: PhaseReorder, db: DbDep) -> list[PhaseRead]:
    return [
        PhaseRead.model_validate(p) for p in service.reorder_phases(db, project_id, body.phase_ids)
    ]


@router.patch("/phases/{phase_id}", response_model=PhaseRead, dependencies=[pm_write])
def update_phase(phase_id: uuid.UUID, body: PhaseUpdate, db: DbDep) -> PhaseRead:
    return PhaseRead.model_validate(service.update_phase(db, phase_id, body))


@router.delete("/phases/{phase_id}", status_code=204, dependencies=[pm_write])
def delete_phase(phase_id: uuid.UUID, db: DbDep) -> None:
    service.delete_phase(db, phase_id)
