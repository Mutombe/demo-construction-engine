from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, detail: str | None = None):
        self.detail = detail or self.__class__.__doc__ or self.code
        super().__init__(self.detail)


class NotFoundError(AppError):
    """Resource not found."""

    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    """Resource conflict."""

    status_code = 409
    code = "conflict"


class DependencyCycleError(ConflictError):
    """Adding this dependency would create a cycle."""

    code = "dependency_cycle"


class UnauthorizedError(AppError):
    """Invalid or missing credentials."""

    status_code = 401
    code = "unauthorized"


class ForbiddenError(AppError):
    """Insufficient permissions."""

    status_code = 403
    code = "forbidden"


class ValidationFailedError(AppError):
    """Domain validation failed."""

    status_code = 422
    code = "validation_failed"


class AiNotConfiguredError(AppError):
    """AI features require ANTHROPIC_API_KEY to be configured."""

    status_code = 503
    code = "ai_not_configured"


class AiUpstreamError(AppError):
    """The AI service returned an error."""

    status_code = 502
    code = "ai_upstream_error"


class AiRateLimitedError(AppError):
    """The AI service is rate limiting requests."""

    status_code = 429
    code = "ai_rate_limited"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "detail": exc.detail}},
            headers=headers,
        )
