import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.enums import IngestionChannel, IngestionDocType, IngestionStatus
from app.common.models import AuditMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


class IngestionItem(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin):
    """A document dropped into the AI inbox.

    `extraction` is the immutable audit copy of what the model said;
    `proposed_action` is mutable working state (draft, gate, corrections, and —
    after approval — the lineage of the posted record). Approval is the ONLY
    path that creates real ERP records.
    """

    __tablename__ = "ingestion_items"
    __table_args__ = (
        Index("ix_ingestion_items_status_created", "status", "created_at"),
        Index("ix_ingestion_items_sha256", "file_sha256"),
    )

    status: Mapped[IngestionStatus] = mapped_column(
        Enum(IngestionStatus, name="ingestion_status", native_enum=True),
        default=IngestionStatus.received,
    )
    channel: Mapped[IngestionChannel] = mapped_column(
        Enum(IngestionChannel, name="ingestion_channel", native_enum=True),
        default=IngestionChannel.upload,
    )
    doc_type: Mapped[IngestionDocType | None] = mapped_column(
        Enum(IngestionDocType, name="ingestion_doc_type", native_enum=True), index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(500))
    file_sha256: Mapped[str] = mapped_column(String(64))
    media_type: Mapped[str] = mapped_column(String(50))
    file_size: Mapped[int] = mapped_column(Integer)
    extraction: Mapped[dict | None] = mapped_column(JSONB)
    proposed_action: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL", use_alter=True)
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
