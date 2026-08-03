from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Request, Response
from fastapi.security import OAuth2PasswordRequestForm

from app.core.config import settings
from app.core.deps import CurrentUser, DbDep
from app.core.exceptions import UnauthorizedError
from app.core.security import create_access_token
from app.modules.auth import service
from app.modules.auth.schemas import LoginRequest, TokenResponse, UserRead
from app.modules.users.models import User

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/auth"


def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=raw_token,
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
        max_age=settings.refresh_token_ttl_days * 24 * 3600,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)


def _token_response(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        expires_in=settings.access_token_ttl_minutes * 60,
        user=UserRead.model_validate(user),
    )


def _login(db, request: Request, response: Response, email: str, password: str) -> TokenResponse:
    user = service.authenticate(db, email, password)
    raw_refresh = service.create_refresh_token(
        db,
        user,
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
    )
    _set_refresh_cookie(response, raw_refresh)
    return _token_response(user)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, response: Response, db: DbDep) -> TokenResponse:
    return _login(db, request, response, body.email, body.password)


@router.post("/token", response_model=TokenResponse, include_in_schema=False)
def login_form(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    request: Request,
    response: Response,
    db: DbDep,
) -> TokenResponse:
    # Form-encoded variant so the Swagger UI "Authorize" button works
    return _login(db, request, response, form.username, form.password)


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    request: Request,
    response: Response,
    db: DbDep,
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> TokenResponse:
    if not refresh_token:
        raise UnauthorizedError("Missing refresh token")
    try:
        user, raw_new = service.rotate_refresh_token(
            db,
            refresh_token,
            user_agent=request.headers.get("user-agent"),
            ip=request.client.host if request.client else None,
        )
    except UnauthorizedError:
        _clear_refresh_cookie(response)
        raise
    _set_refresh_cookie(response, raw_new)
    return _token_response(user)


@router.post("/logout", status_code=204)
def logout(
    response: Response,
    db: DbDep,
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> None:
    if refresh_token:
        service.revoke_refresh_token(db, refresh_token)
    _clear_refresh_cookie(response)


@router.get("/me", response_model=UserRead)
def me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)
