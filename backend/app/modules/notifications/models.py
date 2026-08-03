import uuid

from sqlalchemy import Boolean, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


class Notification(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """In-app notification for one user. type stays a plain string so new
    emit points never need a migration."""

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_unread", "user_id", "is_read", "created_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str | None] = mapped_column(Text)
    link_path: Mapped[str | None] = mapped_column(String(200))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
