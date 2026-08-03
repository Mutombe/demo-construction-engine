"""In-app notifications.

This module deliberately imports nothing from feature modules; feature
services call notify()/notify_roles() at their emit points, so there are no
import cycles. Notifying yourself is always suppressed — exclude the actor.
"""

import uuid
from collections.abc import Iterable

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.common.enums import UserRole
from app.core.exceptions import NotFoundError
from app.modules.notifications.models import Notification
from app.modules.users.models import User


def notify(
    db: Session,
    user_ids: Iterable[uuid.UUID],
    type: str,
    title: str,
    body: str | None = None,
    link: str | None = None,
    exclude: uuid.UUID | None = None,
) -> None:
    for user_id in {u for u in user_ids if u is not None and u != exclude}:
        db.add(
            Notification(user_id=user_id, type=type, title=title, body=body, link_path=link)
        )
    db.flush()


def notify_roles(
    db: Session,
    roles: Iterable[UserRole],
    type: str,
    title: str,
    body: str | None = None,
    link: str | None = None,
    exclude: uuid.UUID | None = None,
) -> None:
    user_ids = db.scalars(
        select(User.id).where(User.role.in_(list(roles)), User.is_active.is_(True))
    )
    notify(db, user_ids, type, title, body, link, exclude)


def list_notifications(
    db: Session, user_id: uuid.UUID, page: int, page_size: int, unread_only: bool = False
) -> tuple[list[Notification], int]:
    query = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        query = query.where(Notification.is_read.is_(False))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = list(
        db.scalars(
            query.order_by(Notification.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return items, total


def unread_count(db: Session, user_id: uuid.UUID) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id, Notification.is_read.is_(False))
        )
        or 0
    )


def mark_read(db: Session, user_id: uuid.UUID, notification_id: uuid.UUID) -> Notification:
    notification = db.get(Notification, notification_id)
    if notification is None or notification.user_id != user_id:
        raise NotFoundError("Notification not found")
    notification.is_read = True
    return notification


def mark_all_read(db: Session, user_id: uuid.UUID) -> int:
    result = db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.is_read.is_(False))
        .values(is_read=True)
    )
    return result.rowcount or 0
