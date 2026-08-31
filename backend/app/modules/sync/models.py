import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


class SyncOperation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One thing a device captured while it had no signal.

    The row is kept whatever happens to it, including when it is refused.
    A phone that has been out of range for a fortnight will send work that
    is stale, duplicated or plainly wrong, and the person who wrote it needs
    to be told which of their entries did not land rather than discovering
    the gap at month end.
    """

    __tablename__ = "sync_operations"
    __table_args__ = (
        # The device's own id for the capture. Unique, which is the whole
        # mechanism: a retry after a dropped connection finds this row and
        # returns the original outcome instead of writing the diary twice.
        Index("ux_sync_operations_client_op", "client_op_id", unique=True),
        Index("ix_sync_operations_user_status", "user_id", "status"),
    )

    client_op_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True))
    device_id: Mapped[str] = mapped_column(String(80))
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    op_type: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)

    # applied | merged | duplicate | rejected
    status: Mapped[str] = mapped_column(String(20), default="applied")
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    detail: Mapped[str | None] = mapped_column(Text)

    # When the person actually wrote it, as against when the network finally
    # allowed it through. Reports about site work should use the first.
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
