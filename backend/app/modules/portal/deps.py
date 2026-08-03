import hashlib
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy import select

from app.core.deps import DbDep
from app.core.exceptions import UnauthorizedError
from app.modules.clients.models import Client
from app.modules.portal.models import ClientAccessToken

# last_used_at is throttled to one write per interval so casual browsing
# doesn't turn every GET into an UPDATE.
_LAST_USED_THROTTLE = timedelta(minutes=5)


def get_portal_client(
    db: DbDep,
    x_portal_token: Annotated[str | None, Header()] = None,
) -> Client:
    if not x_portal_token:
        raise UnauthorizedError("Portal token required")
    token_hash = hashlib.sha256(x_portal_token.encode()).hexdigest()
    token = db.scalar(
        select(ClientAccessToken).where(ClientAccessToken.token_hash == token_hash)
    )
    if token is None or token.revoked_at is not None:
        raise UnauthorizedError("This link is no longer valid")
    if token.expires_at < datetime.now(UTC):
        raise UnauthorizedError("This link has expired")
    now = datetime.now(UTC)
    if token.last_used_at is None or now - token.last_used_at > _LAST_USED_THROTTLE:
        token.last_used_at = now
    client = db.get(Client, token.client_id)
    if client is None:
        raise UnauthorizedError("This link is no longer valid")
    return client


PortalClient = Annotated[Client, Depends(get_portal_client)]
