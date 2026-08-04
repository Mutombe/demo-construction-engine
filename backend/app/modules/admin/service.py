"""Administration: the activity log and user invitations."""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.security import hash_password
from app.modules.admin.models import ActivityLog, UserInvite
from app.modules.users.models import User


def record(
    db: Session,
    user,
    action: str,
    summary: str,
    *,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    link_path: str | None = None,
) -> None:
    """Append one entry to the activity log.

    Never raises into the caller: an audit write failing must not roll back
    the business action it was describing. A missing log line is a smaller
    problem than a refused approval.
    """
    try:
        db.add(
            ActivityLog(
                user_id=getattr(user, "id", None),
                user_name=getattr(user, "full_name", None),
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                summary=summary,
                link_path=link_path,
            )
        )
        db.flush()
    except Exception:  # pragma: no cover - defensive
        pass


def list_activity(
    db: Session,
    page: int,
    page_size: int,
    user_id: uuid.UUID | None = None,
    action: str | None = None,
    entity_type: str | None = None,
) -> tuple[list[ActivityLog], int]:
    query = select(ActivityLog).options(joinedload(ActivityLog.user))
    if user_id is not None:
        query = query.where(ActivityLog.user_id == user_id)
    if action:
        query = query.where(ActivityLog.action == action)
    if entity_type:
        query = query.where(ActivityLog.entity_type == entity_type)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = list(
        db.scalars(
            query.order_by(ActivityLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return rows, total


def distinct_actions(db: Session) -> list[str]:
    """Drives the filter, so it only ever offers actions that exist."""
    return [row for row in db.scalars(select(ActivityLog.action).distinct().order_by(ActivityLog.action))]


# --- Invites -----------------------------------------------------------------


def _invite_status(invite: UserInvite) -> str:
    if invite.accepted_at:
        return "accepted"
    if invite.revoked_at:
        return "revoked"
    if invite.expires_at < datetime.now(timezone.utc):
        return "expired"
    return "pending"


def invite_read(invite: UserInvite):
    from app.modules.admin.schemas import InviteRead

    read = InviteRead.model_validate(invite)
    read.status = _invite_status(invite)
    return read


def invite_url(raw_token: str) -> str:
    # Same convention as the client portal links
    origin = settings.cors_origins[0] if settings.cors_origins else ""
    return f"{origin}/accept-invite/{raw_token}"


def list_invites(db: Session) -> list[UserInvite]:
    return list(db.scalars(select(UserInvite).order_by(UserInvite.created_at.desc())))


def create_invite(db: Session, data, invited_by: uuid.UUID):
    email = data.email.lower().strip()
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise ConflictError("Someone already has an account with that email")
    existing = db.scalar(
        select(UserInvite).where(
            func.lower(UserInvite.email) == email,
            UserInvite.accepted_at.is_(None),
            UserInvite.revoked_at.is_(None),
        )
    )
    if existing and _invite_status(existing) == "pending":
        raise ConflictError(
            "That email already has a pending invite. Revoke it first to send a new one"
        )

    raw = secrets.token_urlsafe(32)
    invite = UserInvite(
        email=email,
        full_name=data.full_name,
        role=data.role,
        token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        expires_at=datetime.now(timezone.utc) + timedelta(days=data.expires_in_days),
        invited_by=invited_by,
    )
    db.add(invite)
    db.flush()
    return invite, raw


def revoke_invite(db: Session, invite_id: uuid.UUID) -> UserInvite:
    invite = db.get(UserInvite, invite_id)
    if invite is None:
        raise NotFoundError("Invite not found")
    if _invite_status(invite) != "pending":
        raise ConflictError("Only a pending invite can be revoked")
    invite.revoked_at = datetime.now(timezone.utc)
    db.flush()
    return invite


def accept_invite(db: Session, data) -> User:
    """Turn a valid invite into an account.

    Unauthenticated by design, since the person accepting has no account yet.
    The token is the only credential, which is why it is single-use and
    stored hashed.
    """
    token_hash = hashlib.sha256(data.token.encode()).hexdigest()
    invite = db.scalar(select(UserInvite).where(UserInvite.token_hash == token_hash))
    if invite is None:
        raise NotFoundError("That invite link is not valid")
    status = _invite_status(invite)
    if status != "pending":
        raise ValidationFailedError(f"That invite has already been {status}")
    if db.scalar(select(User).where(func.lower(User.email) == invite.email)):
        raise ConflictError("An account with that email already exists")

    user = User(
        email=invite.email,
        full_name=invite.full_name,
        role=invite.role,
        hashed_password=hash_password(data.password),
        is_active=True,
    )
    db.add(user)
    invite.accepted_at = datetime.now(timezone.utc)
    db.flush()
    record(
        db,
        user,
        "user_joined",
        f"{user.full_name} accepted an invite as {user.role.value}",
        entity_type="user",
        entity_id=user.id,
    )
    return user
