import uuid

from fastapi import APIRouter, Depends

from app.common.enums import UserRole
from app.common.pagination import PageParamsDep
from app.common.schemas import Page
from app.core.deps import CurrentUser, DbDep, require_roles
from app.modules.clients import service
from app.modules.clients.schemas import ClientCreate, ClientRead, ClientUpdate

router = APIRouter(prefix="/clients", tags=["clients"])

pm_write = Depends(require_roles(UserRole.project_manager))


@router.get("", response_model=Page[ClientRead])
def list_clients(db: DbDep, params: PageParamsDep, search: str | None = None) -> Page[ClientRead]:
    clients, total = service.list_clients(db, params.page, params.page_size, search)
    return Page(
        items=[ClientRead.model_validate(c) for c in clients],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.post("", response_model=ClientRead, status_code=201)
def create_client(
    body: ClientCreate, db: DbDep, user=Depends(require_roles(UserRole.project_manager))
) -> ClientRead:
    return ClientRead.model_validate(service.create_client(db, body, user.id))


@router.get("/{client_id}", response_model=ClientRead)
def get_client(client_id: uuid.UUID, db: DbDep) -> ClientRead:
    return ClientRead.model_validate(service.get_client(db, client_id))


@router.patch("/{client_id}", response_model=ClientRead, dependencies=[pm_write])
def update_client(client_id: uuid.UUID, body: ClientUpdate, db: DbDep) -> ClientRead:
    return ClientRead.model_validate(service.update_client(db, client_id, body))


@router.delete("/{client_id}", status_code=204, dependencies=[pm_write])
def delete_client(client_id: uuid.UUID, db: DbDep, user: CurrentUser) -> None:
    service.delete_client(db, client_id, user)
