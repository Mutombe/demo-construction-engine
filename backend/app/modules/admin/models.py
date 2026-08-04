import uuid
from datetime import datetime

from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.enums import UserRole
from app.common.models import TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base
from sqlalchemy import Enum as SaEnum


class ActivityLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Who did what, and when.

    Append-only by construction: there is no update or delete path. Records
    the human-readable summary alongside the entity reference so an entry
    still means something after the record it describes is gone.
    """

    __tablename__ = "activity_logs"
    __table_args__ = (
        Index("ix_activity_logs_entity", "entity_type", "entity_id"),
        Index("ix_activity_logs_created", "created_at"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    # Snapshotted: the log must still read correctly if the user is removed
    user_name: Mapped[str | None] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(60), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    summary: Mapped[str] = mapped_column(Text)
    link_path: Mapped[str | None] = mapped_column(String(200))

    user = relationship("User")


class UserInvite(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A pending invitation to join.

    Only the hash of the token is stored, exactly like the client portal
    links: the raw token is shown once at creation and cannot be recovered.
    """

    __tablename__ = "user_invites"

    email: Mapped[str] = mapped_column(String(255), index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[UserRole] = mapped_column(
        SaEnum(UserRole, name="user_role", native_enum=True)
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL", use_alter=True)
    )


class DeletedRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A deleted row, kept whole so it can be put back.

    Deliberately an archive table rather than a `deleted_at` column on every
    model. Twenty models would each need the column, a migration, and a filter
    on every query that reads them — and one missed filter silently resurrects
    a deleted record in a report. Here the row genuinely leaves its table, so
    nothing downstream can be wrong about it, and the recovery path is one
    place instead of twenty.
    """

    __tablename__ = "deleted_records"

    entity_type: Mapped[str] = mapped_column(String(40), index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), index=True)
    table_name: Mapped[str] = mapped_column(String(60))
    # What a person would recognise it by, e.g. "PO-0042 — Blue Circle"
    label: Mapped[str] = mapped_column(Text)
    project_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    # [{"table": "...", "rows": [{col: value}]}], parents first
    payload: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    row_count: Mapped[int] = mapped_column(default=1)
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    deleted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL", use_alter=True)
    )
    deleted_by_name: Mapped[str | None] = mapped_column(String(120))
    restored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # False when the delete was too large to capture in full; keeping the
    # entry is still worth it as a record of what went, but restore is off.
    restorable: Mapped[bool] = mapped_column(Boolean, default=True)
