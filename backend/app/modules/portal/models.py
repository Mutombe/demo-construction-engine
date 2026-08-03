import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models import AuditMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


class ClientAccessToken(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin):
    """PM-generated portal access link for a client.

    Only the sha256 hash is stored; the raw token is shown exactly once at
    creation. Anyone holding the link can read that client's portal until it
    expires or a PM revokes it.
    """

    __tablename__ = "client_access_tokens"

    client_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    label: Mapped[str] = mapped_column(String(120))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    client = relationship("Client")
