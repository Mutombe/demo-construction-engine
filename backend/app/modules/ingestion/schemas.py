import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.common.enums import IngestionChannel, IngestionDocType, IngestionStatus


class IngestionItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: IngestionStatus
    channel: IngestionChannel
    doc_type: IngestionDocType | None
    project_id: uuid.UUID | None
    original_filename: str
    media_type: str
    file_size: int
    file_sha256: str
    extraction: dict[str, Any] | None
    proposed_action: dict[str, Any] | None
    error: str | None
    rejection_reason: str | None
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class IngestionUploadResponse(BaseModel):
    item: IngestionItemRead
    duplicate_ids: list[uuid.UUID]


class IngestionDraftRequest(BaseModel):
    """Human corrections keyed by extraction field name (e.g. \"total_amount\")."""

    corrections: dict[str, Any] = Field(default_factory=dict)


class IngestionRejectRequest(BaseModel):
    reason: str = Field(min_length=1)
