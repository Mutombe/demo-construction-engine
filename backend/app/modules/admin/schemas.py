import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.common.enums import UserRole


class ActivityLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID | None
    user_name: str | None
    action: str
    entity_type: str | None
    entity_id: uuid.UUID | None
    summary: str
    link_path: str | None
    created_at: datetime


class InviteCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=120)
    role: UserRole
    expires_in_days: int = Field(default=7, ge=1, le=90)


class InviteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
    status: str = "pending"  # pending | accepted | revoked | expired


class InviteCreated(InviteRead):
    """The raw link is returned once at creation and never again."""

    invite_url: str


class InviteAccept(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=128)


class DeletedRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    label: str
    project_id: uuid.UUID | None
    row_count: int
    deleted_at: datetime
    deleted_by_name: str | None
    restorable: bool
