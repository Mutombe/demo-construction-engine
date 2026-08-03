import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.modules.clients.models import Client
from app.modules.clients.schemas import ClientCreate, ClientUpdate
from app.modules.projects.models import Project


def list_clients(
    db: Session, page: int, page_size: int, search: str | None = None
) -> tuple[list[Client], int]:
    query = select(Client)
    if search:
        query = query.where(Client.name.ilike(f"%{search}%"))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    clients = list(
        db.scalars(query.order_by(Client.name).offset((page - 1) * page_size).limit(page_size))
    )
    return clients, total


def get_client(db: Session, client_id: uuid.UUID) -> Client:
    client = db.get(Client, client_id)
    if client is None:
        raise NotFoundError("Client not found")
    return client


def create_client(db: Session, data: ClientCreate, created_by: uuid.UUID) -> Client:
    if db.scalar(select(Client).where(Client.name == data.name)):
        raise ConflictError("A client with this name already exists")
    client = Client(**data.model_dump(), created_by=created_by)
    db.add(client)
    db.flush()
    return client


def update_client(db: Session, client_id: uuid.UUID, data: ClientUpdate) -> Client:
    client = get_client(db, client_id)
    updates = data.model_dump(exclude_unset=True)
    if (
        "name" in updates
        and updates["name"] != client.name
        and db.scalar(select(Client).where(Client.name == updates["name"]))
    ):
        raise ConflictError("A client with this name already exists")
    for field, value in updates.items():
        setattr(client, field, value)
    return client


def delete_client(db: Session, client_id: uuid.UUID) -> None:
    client = get_client(db, client_id)
    project_count = (
        db.scalar(select(func.count()).select_from(Project).where(Project.client_id == client_id))
        or 0
    )
    if project_count > 0:
        raise ConflictError(f"Client has {project_count} project(s) and cannot be deleted")
    db.delete(client)
