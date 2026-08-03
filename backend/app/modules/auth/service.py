import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import UnauthorizedError
from app.core.security import (
    generate_refresh_token,
    hash_refresh_token,
    refresh_token_expiry,
    verify_password,
)
from app.modules.users.models import RefreshToken, User


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email.lower()))
    if user is None or not verify_password(password, user.hashed_password):
        raise UnauthorizedError("Incorrect email or password")
    if not user.is_active:
        raise UnauthorizedError("Account is deactivated")
    user.last_login_at = datetime.now(UTC)
    return user


def create_refresh_token(
    db: Session,
    user: User,
    user_agent: str | None = None,
    ip: str | None = None,
) -> str:
    raw, token_hash = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=refresh_token_expiry(),
            user_agent=user_agent[:255] if user_agent else None,
            ip=ip,
        )
    )
    db.flush()
    return raw


def rotate_refresh_token(
    db: Session,
    raw_token: str,
    user_agent: str | None = None,
    ip: str | None = None,
) -> tuple[User, str]:
    """Validate + rotate. Reuse of an already-rotated token revokes the whole chain
    (refresh token theft detection)."""
    token_hash = hash_refresh_token(raw_token)
    token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    if token is None:
        raise UnauthorizedError("Invalid refresh token")

    now = datetime.now(UTC)
    if token.revoked_at is not None:
        _revoke_descendants(db, token)
        # The request will end in a 401, which rolls the session back — the
        # revocation must survive that, so commit it here explicitly.
        db.commit()
        raise UnauthorizedError("Refresh token reuse detected — all sessions revoked")
    if token.expires_at < now:
        raise UnauthorizedError("Refresh token expired")

    user = db.get(User, token.user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive")

    raw_new, new_hash = generate_refresh_token()
    new_token = RefreshToken(
        user_id=user.id,
        token_hash=new_hash,
        expires_at=refresh_token_expiry(),
        user_agent=user_agent[:255] if user_agent else None,
        ip=ip,
    )
    db.add(new_token)
    db.flush()
    token.revoked_at = now
    token.replaced_by_id = new_token.id
    return user, raw_new


def revoke_refresh_token(db: Session, raw_token: str) -> None:
    token_hash = hash_refresh_token(raw_token)
    token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    if token is not None and token.revoked_at is None:
        token.revoked_at = datetime.now(UTC)


def revoke_all_for_user(db: Session, user_id: uuid.UUID) -> None:
    now = datetime.now(UTC)
    tokens = db.scalars(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
        )
    )
    for t in tokens:
        t.revoked_at = now


def _revoke_descendants(db: Session, token: RefreshToken) -> None:
    now = datetime.now(UTC)
    current = token
    while current.replaced_by_id is not None:
        nxt = db.get(RefreshToken, current.replaced_by_id)
        if nxt is None:
            break
        if nxt.revoked_at is None:
            nxt.revoked_at = now
        current = nxt
