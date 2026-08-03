import uuid

from fastapi import APIRouter, Depends

from app.common.pagination import PageParamsDep
from app.common.schemas import Page
from app.core.deps import CurrentUser, DbDep, require_roles
from app.modules.users import service
from app.modules.users.schemas import MeUpdate, UserCreate, UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])

admin_only = Depends(require_roles())  # only admin passes (admin bypasses role list)


@router.get("", response_model=Page[UserRead], dependencies=[admin_only])
def list_users(db: DbDep, params: PageParamsDep) -> Page[UserRead]:
    users, total = service.list_users(db, params.page, params.page_size)
    return Page(
        items=[UserRead.model_validate(u) for u in users],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.post("", response_model=UserRead, status_code=201, dependencies=[admin_only])
def create_user(body: UserCreate, db: DbDep) -> UserRead:
    return UserRead.model_validate(service.create_user(db, body))


@router.patch("/me", response_model=UserRead)
def update_me(body: MeUpdate, db: DbDep, user: CurrentUser) -> UserRead:
    return UserRead.model_validate(service.update_me(db, user, body))


@router.get("/{user_id}", response_model=UserRead, dependencies=[admin_only])
def get_user(user_id: uuid.UUID, db: DbDep) -> UserRead:
    return UserRead.model_validate(service.get_user(db, user_id))


@router.patch("/{user_id}", response_model=UserRead, dependencies=[admin_only])
def update_user(user_id: uuid.UUID, body: UserUpdate, db: DbDep) -> UserRead:
    return UserRead.model_validate(service.update_user(db, user_id, body))
