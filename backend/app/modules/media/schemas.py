import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.common.enums import MediaFolder


class MediaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    folder: MediaFolder
    original_filename: str
    media_type: str
    file_size: int
    file_sha256: str
    caption: str | None
    has_thumbnail: bool = False
    created_by: uuid.UUID | None
    created_at: datetime


class MediaUpdate(BaseModel):
    caption: str | None = Field(default=None, max_length=255)
    folder: MediaFolder | None = None


class FolderCounts(BaseModel):
    counts: dict[str, int]
    total: int
