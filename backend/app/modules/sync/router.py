import uuid

from fastapi import APIRouter

from app.core.deps import CurrentUser, DbDep
from app.modules.sync import service
from app.modules.sync.schemas import Bootstrap, SyncPush, SyncPushResult, SyncResult

router = APIRouter(prefix="/sync", tags=["sync"])


@router.get("/bootstrap/{project_id}", response_model=Bootstrap)
def get_bootstrap(project_id: uuid.UUID, db: DbDep) -> Bootstrap:
    """The small pack a device keeps so its forms still work with no signal."""
    return service.bootstrap(db, project_id)


@router.post("/push", response_model=SyncPushResult)
def push(body: SyncPush, db: DbDep, user: CurrentUser) -> SyncPushResult:
    """Hand over everything a device captured while it was out of range.

    Safe to call with the same backlog twice: captures already taken come
    back marked `duplicate` rather than being written again.
    """
    return service.push(db, body, user)


@router.get("/rejected", response_model=list[SyncResult])
def list_rejected(db: DbDep, user: CurrentUser, limit: int = 50) -> list[SyncResult]:
    """What this person sent up that could not be saved, and why."""
    return service.rejected_for(db, user, limit)
