import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, UnauthorizedError
from app.core.security import hash_password, verify_password
from app.modules.auth.service import revoke_all_for_user
from app.modules.users.models import User
from app.modules.users.schemas import MeUpdate, UserCreate, UserUpdate


def list_users(db: Session, page: int, page_size: int) -> tuple[list[User], int]:
    total = db.scalar(select(func.count()).select_from(User)) or 0
    users = list(
        db.scalars(
            select(User).order_by(User.full_name).offset((page - 1) * page_size).limit(page_size)
        )
    )
    return users, total


def get_user(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found")
    return user


def create_user(db: Session, data: UserCreate) -> User:
    email = data.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise ConflictError("A user with this email already exists")
    user = User(
        email=email,
        full_name=data.full_name,
        hashed_password=hash_password(data.password),
        role=data.role,
    )
    db.add(user)
    db.flush()
    return user


def update_user(db: Session, user_id: uuid.UUID, data: UserUpdate) -> User:
    user = get_user(db, user_id)
    if data.full_name is not None:
        user.full_name = data.full_name
    if data.role is not None:
        user.role = data.role
    if data.is_active is not None:
        user.is_active = data.is_active
        if not data.is_active:
            revoke_all_for_user(db, user.id)
    if data.password is not None:
        user.hashed_password = hash_password(data.password)
        revoke_all_for_user(db, user.id)
    return user


def update_me(db: Session, user: User, data: MeUpdate) -> User:
    if data.full_name is not None:
        user.full_name = data.full_name
    if data.password is not None:
        if not data.current_password or not verify_password(
            data.current_password, user.hashed_password
        ):
            raise UnauthorizedError("Current password is incorrect")
        user.hashed_password = hash_password(data.password)
        revoke_all_for_user(db, user.id)
    return user
