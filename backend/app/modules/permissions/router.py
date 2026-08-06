import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.common.enums import UserRole
from app.core.deps import CurrentUser, DbDep, require_roles
from app.core.exceptions import NotFoundError
from app.modules.permissions import service
from app.modules.permissions.defaults import (
    ACTION_LABELS,
    MODULE_LABELS,
    PERMISSIONS,
    all_permissions,
)
from app.modules.users.models import User

router = APIRouter(prefix="/permissions", tags=["permissions"])
settings_admin = Depends(require_roles(UserRole.admin))


class MatrixUpdate(BaseModel):
    role: UserRole
    permission: str = Field(max_length=40)
    allowed: bool


class OverrideUpdate(BaseModel):
    permission: str = Field(max_length=40)
    # None clears the exception and puts the person back on their role.
    allowed: bool | None = None


@router.get("/catalogue", response_model=dict, dependencies=[settings_admin])
def get_catalogue() -> dict:
    """What can be granted, and what to call it on screen."""
    return {
        "modules": [
            {
                "key": module,
                "label": MODULE_LABELS.get(module, module),
                "actions": [
                    {"key": action, "label": ACTION_LABELS.get(action, action),
                     "permission": f"{module}:{action}"}
                    for action in actions
                ],
            }
            for module, actions in PERMISSIONS.items()
        ],
        "roles": [role.value for role in UserRole],
        "permissions": all_permissions(),
    }


@router.get("/matrix", response_model=dict[str, list[str]], dependencies=[settings_admin])
def get_matrix(db: DbDep) -> dict[str, list[str]]:
    return service.role_matrix(db)


@router.put("/matrix", response_model=dict[str, list[str]])
def update_matrix(body: MatrixUpdate, db: DbDep, _=settings_admin) -> dict[str, list[str]]:
    """Admin is not editable here on purpose: an editable matrix with no floor
    is one bad click away from a company with nobody who can fix it."""
    if body.role is UserRole.admin:
        from app.core.exceptions import ConflictError

        raise ConflictError("Administrators always keep every permission")
    service.set_role_permission(db, body.role, body.permission, body.allowed)
    return service.role_matrix(db)


@router.get("/users/{user_id}", response_model=dict)
def get_user_permissions(user_id: uuid.UUID, db: DbDep, _=settings_admin) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found")
    return {
        "user_id": user.id,
        "role": user.role.value,
        "effective": sorted(service.effective_permissions(db, user)),
        "overrides": service.overrides_for(db, user.id),
    }


@router.put("/users/{user_id}", response_model=dict)
def update_user_permissions(
    user_id: uuid.UUID, body: OverrideUpdate, db: DbDep, _=settings_admin
) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found")
    service.set_user_override(db, user_id, body.permission, body.allowed)
    return {
        "user_id": user.id,
        "role": user.role.value,
        "effective": sorted(service.effective_permissions(db, user)),
        "overrides": service.overrides_for(db, user.id),
    }


@router.get("/me", response_model=list[str])
def my_permissions(db: DbDep, user: CurrentUser) -> list[str]:
    """What the signed-in person may do. The frontend gates on this rather
    than on a table compiled into the bundle, so an edit takes effect on the
    next page load instead of the next deploy."""
    return sorted(service.effective_permissions(db, user))
