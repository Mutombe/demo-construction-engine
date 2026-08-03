import uuid
from datetime import datetime

import uuid_utils
from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, declared_attr, mapped_column


def uuid7() -> uuid.UUID:
    # uuid_utils returns its own UUID type; convert to stdlib for driver compatibility
    return uuid.UUID(bytes=uuid_utils.uuid7().bytes)


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid7)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class AuditMixin:
    @declared_attr
    def created_by(cls) -> Mapped[uuid.UUID | None]:
        return mapped_column(
            PG_UUID(as_uuid=True),
            ForeignKey("users.id", ondelete="SET NULL", use_alter=True),
            nullable=True,
        )
