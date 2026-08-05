import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models import TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


class Comment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A message on a record.

    Polymorphic on (entity_type, entity_id) exactly like media files, so one
    thread mechanism covers tasks, projects, POs and everything else rather
    than a comments table per module.
    """

    __tablename__ = "comments"
    __table_args__ = (Index("ix_comments_entity", "entity_type", "entity_id", "created_at"),)

    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), index=True)
    body: Mapped[str] = mapped_column(Text)
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    # Snapshotted so a thread still reads correctly after someone leaves
    author_name: Mapped[str | None] = mapped_column(String(120))
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    author = relationship("User")
