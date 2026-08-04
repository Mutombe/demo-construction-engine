import uuid

from fastapi import APIRouter, Depends

from app.common.enums import UserRole
from app.common.pagination import PageParamsDep
from app.common.schemas import Page
from app.core.deps import CurrentUser, DbDep, require_roles
from app.modules.admin import service, trash
from app.modules.admin.schemas import (
    ActivityLogRead,
    DeletedRecordRead,
    InviteAccept,
    InviteCreate,
    InviteCreated,
    InviteRead,
)
from app.modules.users.schemas import UserRead

router = APIRouter(prefix="/admin", tags=["admin"])

admin_only = Depends(require_roles(UserRole.admin))


@router.get("/activity", response_model=Page[ActivityLogRead], dependencies=[admin_only])
def list_activity(
    db: DbDep,
    params: PageParamsDep,
    user_id: uuid.UUID | None = None,
    action: str | None = None,
    entity_type: str | None = None,
) -> Page[ActivityLogRead]:
    rows, total = service.list_activity(
        db, params.page, params.page_size, user_id, action, entity_type
    )
    return Page(items=rows, total=total, page=params.page, page_size=params.page_size)


@router.get("/activity/actions", response_model=list[str], dependencies=[admin_only])
def list_activity_actions(db: DbDep) -> list[str]:
    return service.distinct_actions(db)


@router.get("/invites", response_model=list[InviteRead], dependencies=[admin_only])
def list_invites(db: DbDep) -> list[InviteRead]:
    return [service.invite_read(i) for i in service.list_invites(db)]


@router.post("/invites", response_model=InviteCreated, status_code=201)
def create_invite(
    body: InviteCreate, db: DbDep, user: CurrentUser, _=admin_only
) -> InviteCreated:
    """The link is returned once here and cannot be recovered afterwards."""
    invite, raw = service.create_invite(db, body, user.id)
    read = service.invite_read(invite)
    service.record(
        db,
        user,
        "invite_sent",
        f"Invited {invite.email} as {invite.role.value}",
        entity_type="invite",
        entity_id=invite.id,
    )
    return InviteCreated(**read.model_dump(), invite_url=service.invite_url(raw))


@router.post("/invites/{invite_id}/revoke", response_model=InviteRead)
def revoke_invite(
    invite_id: uuid.UUID, db: DbDep, user: CurrentUser, _=admin_only
) -> InviteRead:
    invite = service.revoke_invite(db, invite_id)
    service.record(
        db,
        user,
        "invite_revoked",
        f"Revoked the invite for {invite.email}",
        entity_type="invite",
        entity_id=invite.id,
    )
    return service.invite_read(invite)


@router.get("/trash", response_model=Page[DeletedRecordRead], dependencies=[admin_only])
def list_trash(
    db: DbDep, params: PageParamsDep, entity_type: str | None = None
) -> Page[DeletedRecordRead]:
    rows, total = trash.list_deleted(db, params.page, params.page_size, entity_type)
    return Page(items=rows, total=total, page=params.page, page_size=params.page_size)


@router.get("/trash/types", response_model=list[str], dependencies=[admin_only])
def list_trash_types(db: DbDep) -> list[str]:
    return trash.distinct_types(db)


@router.post("/trash/{record_id}/restore", response_model=DeletedRecordRead)
def restore_deleted(
    record_id: uuid.UUID, db: DbDep, user: CurrentUser, _=admin_only
) -> DeletedRecordRead:
    record = trash.restore(db, record_id)
    service.record(
        db,
        user,
        "record_restored",
        f"Restored {record.entity_type.replace('_', ' ')} {record.label}",
        entity_type=record.entity_type,
        entity_id=record.entity_id,
    )
    return DeletedRecordRead.model_validate(record)


@router.delete("/trash/{record_id}", status_code=204)
def purge_deleted(record_id: uuid.UUID, db: DbDep, user: CurrentUser, _=admin_only) -> None:
    """Empty one entry for good. There is nothing after this."""
    record = trash.purge(db, record_id)
    service.record(
        db,
        user,
        "record_purged",
        f"Permanently removed {record.entity_type.replace('_', ' ')} {record.label}",
        entity_type=record.entity_type,
        entity_id=record.entity_id,
    )


# Deliberately unauthenticated: the person accepting has no account yet, and
# the single-use hashed token is the credential.
public_router = APIRouter(prefix="/invites", tags=["admin"])


@public_router.post("/accept", response_model=UserRead)
def accept_invite(body: InviteAccept, db: DbDep) -> UserRead:
    return UserRead.model_validate(service.accept_invite(db, body))
