from pydantic import BaseModel, Field

from app.common.enums import UserRole
from app.modules.auth.schemas import EMAIL_PATTERN, UserRead

__all__ = ["UserRead", "UserCreate", "UserUpdate", "MeUpdate"]


class UserCreate(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN)
    full_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.viewer


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: UserRole | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    is_active: bool | None = None


class MeUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    current_password: str | None = None
