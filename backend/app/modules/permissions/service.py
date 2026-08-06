"""Resolving what someone may actually do.

Two layers: the role matrix, then that person's own exceptions on top. The
resolution is deliberately dull — role grants, override adjusts, admin wins —
because access control that needs explaining is access control nobody checks.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.enums import UserRole
from app.core.exceptions import ValidationFailedError
from app.modules.permissions.defaults import DEFAULT_MATRIX, all_permissions
from app.modules.permissions.models import RolePermission, UserPermissionOverride


def ensure_seeded(db: Session) -> int:
    """Writes the starting matrix once.

    Idempotent, and deliberately additive: it fills an empty table rather than
    resetting a matrix somebody has since edited.
    """
    if db.scalar(select(RolePermission).limit(1)) is not None:
        return 0
    rows = 0
    for role, permissions in DEFAULT_MATRIX.items():
        for permission in sorted(set(permissions)):
            db.add(RolePermission(role=role, permission=permission))
            rows += 1
    db.flush()
    return rows


def role_matrix(db: Session) -> dict[str, list[str]]:
    ensure_seeded(db)
    matrix: dict[str, list[str]] = {role.value: [] for role in UserRole}
    for row in db.scalars(select(RolePermission)):
        matrix.setdefault(row.role.value, []).append(row.permission)
    return {role: sorted(perms) for role, perms in matrix.items()}


def set_role_permission(db: Session, role: UserRole, permission: str, allowed: bool) -> None:
    _check_known(permission)
    existing = db.scalar(
        select(RolePermission).where(
            RolePermission.role == role, RolePermission.permission == permission
        )
    )
    if allowed and existing is None:
        db.add(RolePermission(role=role, permission=permission))
    elif not allowed and existing is not None:
        db.delete(existing)
    db.flush()


def set_user_override(
    db: Session, user_id: uuid.UUID, permission: str, allowed: bool | None
) -> None:
    """`allowed=None` clears the exception and puts the person back on their role."""
    _check_known(permission)
    existing = db.scalar(
        select(UserPermissionOverride).where(
            UserPermissionOverride.user_id == user_id,
            UserPermissionOverride.permission == permission,
        )
    )
    if allowed is None:
        if existing is not None:
            db.delete(existing)
    elif existing is None:
        db.add(UserPermissionOverride(user_id=user_id, permission=permission, allowed=allowed))
    else:
        existing.allowed = allowed
    db.flush()


def overrides_for(db: Session, user_id: uuid.UUID) -> dict[str, bool]:
    return {
        row.permission: row.allowed
        for row in db.scalars(
            select(UserPermissionOverride).where(UserPermissionOverride.user_id == user_id)
        )
    }


def effective_permissions(db: Session, user) -> set[str]:
    """What this person may do, right now.

    Admin keeps everything unconditionally. That is the escape hatch: an
    editable matrix with no floor is one bad click away from a company with
    nobody who can fix it.
    """
    if user.role is UserRole.admin:
        return set(all_permissions())

    ensure_seeded(db)
    granted = {
        row.permission
        for row in db.scalars(select(RolePermission).where(RolePermission.role == user.role))
    }
    for permission, allowed in overrides_for(db, user.id).items():
        if allowed:
            granted.add(permission)
        else:
            granted.discard(permission)
    return granted


def can(db: Session, user, permission: str) -> bool:
    return permission in effective_permissions(db, user)


def _check_known(permission: str) -> None:
    if permission not in set(all_permissions()):
        raise ValidationFailedError(f"{permission} is not a permission this system has")
