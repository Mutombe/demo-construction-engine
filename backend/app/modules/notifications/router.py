import uuid

from fastapi import APIRouter

from app.common.pagination import PageParamsDep
from app.common.schemas import Page
from app.core.deps import CurrentUser, DbDep
from app.modules.notifications import service
from app.modules.notifications.schemas import NotificationRead, UnreadCount

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=Page[NotificationRead])
def list_notifications(
    db: DbDep, user: CurrentUser, params: PageParamsDep, unread_only: bool = False
) -> Page[NotificationRead]:
    items, total = service.list_notifications(
        db, user.id, params.page, params.page_size, unread_only
    )
    return Page(
        items=[NotificationRead.model_validate(n) for n in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get("/unread-count", response_model=UnreadCount)
def get_unread_count(db: DbDep, user: CurrentUser) -> UnreadCount:
    return UnreadCount(count=service.unread_count(db, user.id))


@router.post("/{notification_id}/read", response_model=NotificationRead)
def mark_notification_read(
    notification_id: uuid.UUID, db: DbDep, user: CurrentUser
) -> NotificationRead:
    return NotificationRead.model_validate(service.mark_read(db, user.id, notification_id))


@router.post("/read-all", response_model=UnreadCount)
def mark_all_notifications_read(db: DbDep, user: CurrentUser) -> UnreadCount:
    service.mark_all_read(db, user.id)
    return UnreadCount(count=0)
