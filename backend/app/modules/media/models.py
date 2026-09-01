import uuid

from sqlalchemy import Enum, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.enums import MediaFolder
from app.common.models import AuditMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


class MediaFile(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin):
    """One attached file in the central media library.

    Attachment is polymorphic: (entity_type, entity_id) points at any record
    the media registry allows (projects, stock items, expense claims, …).
    Files live under settings.media_root and are served ONLY through the
    authenticated endpoints — never a static mount. Images carry a Pillow
    thumbnail alongside the original.
    """

    __tablename__ = "media_files"
    __table_args__ = (
        Index("ix_media_files_entity", "entity_type", "entity_id"),
        Index("ix_media_files_sha256", "file_sha256"),
        # The id a device gave the photo before it had signal. Unique, so a
        # retry after a dropped upload returns the photo already stored
        # rather than filing the same one twice.
        Index("ux_media_files_client_op", "client_op_id", unique=True,
              postgresql_where=text("client_op_id IS NOT NULL")),
    )

    client_op_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    entity_type: Mapped[str] = mapped_column(String(30))
    entity_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True))
    folder: Mapped[MediaFolder] = mapped_column(
        Enum(MediaFolder, name="media_folder", native_enum=True), default=MediaFolder.other
    )
    original_filename: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(500))
    thumb_path: Mapped[str | None] = mapped_column(String(500))
    file_sha256: Mapped[str] = mapped_column(String(64))
    media_type: Mapped[str] = mapped_column(String(100))
    file_size: Mapped[int] = mapped_column(Integer)
    caption: Mapped[str | None] = mapped_column(String(255))
