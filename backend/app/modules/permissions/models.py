import uuid

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.enums import UserRole
from app.common.models import TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base
from sqlalchemy import Enum as SaEnum


class RolePermission(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """What a role may do, as data rather than as code.

    A row per (role, permission) that is allowed. Absence is denial, so the
    table only ever states what is permitted and there is no way to end up
    with a row that says both.
    """

    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role", "permission"),)

    role: Mapped[UserRole] = mapped_column(
        SaEnum(UserRole, name="user_role", native_enum=True), index=True
    )
    permission: Mapped[str] = mapped_column(String(40), index=True)


class UserPermissionOverride(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One person, adjusted off their role.

    Kept separate from the role matrix so an exception stays visibly an
    exception: granting a storeman one extra thing should not quietly widen
    every storeman in the company.
    """

    __tablename__ = "user_permission_overrides"
    __table_args__ = (UniqueConstraint("user_id", "permission"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    permission: Mapped[str] = mapped_column(String(40), index=True)
    # True grants something the role lacks, False takes away something it has.
    allowed: Mapped[bool] = mapped_column(Boolean, default=True)
