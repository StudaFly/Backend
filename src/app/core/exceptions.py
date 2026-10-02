import logging
import socket

import redis.exceptions as redis_errors
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import exc as sa_errors
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

_HTTP_ERROR_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "TOO_MANY_REQUESTS",
}


class StudaFlyException(Exception):
    def __init__(
        self,
        message: str,
        code: str,
        status_code: int = 400,
        headers: dict[str, str] | None = None,
    ):
        self.message = message
        self.code = code
        self.status_code = status_code
        self.headers = headers
        super().__init__(message)


class NotFoundError(StudaFlyException):
    def __init__(self, message: str = "Resource not found"):
        super().__init__(
            message=message,
            code="NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class ForbiddenError(StudaFlyException):
    def __init__(self, message: str = "Access forbidden"):
        super().__init__(
            message=message,
            code="FORBIDDEN",
            status_code=status.HTTP_403_FORBIDDEN,
        )


class ConflictError(StudaFlyException):
    def __init__(self, message: str):
        super().__init__(
            message=message,
            code="CONFLICT",
            status_code=status.HTTP_409_CONFLICT,
        )


class UnauthorizedError(StudaFlyException):
    def __init__(self, message: str = "Authentication required"):
        super().__init__(
            message=message,
            code="UNAUTHORIZED",
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Bearer"},
        )


def _error_response(
    status_code: int,
    code: str,
    message: str,
    details=None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    error = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return JSONResponse(status_code=status_code, content={"error": error}, headers=headers)


def _format_validation_errors(exc: RequestValidationError) -> tuple[str, list[dict]]:
    details = [
        {"loc": list(err.get("loc", ())), "msg": err.get("msg", ""), "type": err.get("type", "")}
        for err in exc.errors()
    ]
    if not details:
        return "Invalid request", details
    first = details[0]
    field = ".".join(str(part) for part in first["loc"] if part not in ("body", "query", "path"))
    msg = first["msg"].removeprefix("Value error, ")
    return (f"{field}: {msg}" if field else msg), details


def add_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StudaFlyException)
    async def studafly_exception_handler(request: Request, exc: StudaFlyException):
        return _error_response(exc.status_code, exc.code, exc.message, headers=exc.headers)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        message = exc.detail if isinstance(exc.detail, str) else "HTTP error"
        code = _HTTP_ERROR_CODES.get(exc.status_code, "HTTP_ERROR")
        return _error_response(exc.status_code, code, message, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        message, details = _format_validation_errors(exc)
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "VALIDATION_ERROR", message, details=details
        )

    @app.exception_handler(NotImplementedError)
    async def not_implemented_handler(request: Request, exc: NotImplementedError):
        return _error_response(
            status.HTTP_501_NOT_IMPLEMENTED,
            "NOT_IMPLEMENTED",
            "This feature is not available yet",
        )

    async def database_unavailable(request: Request, exc: Exception):
        from src.app.core.services_status import DATABASE_TARGET, START_HINT

        logger.error(
            "PostgreSQL unreachable at %s (%s): %s", DATABASE_TARGET, type(exc).__name__, exc
        )
        return _error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "DATABASE_UNAVAILABLE",
            f"The database is unreachable ({DATABASE_TARGET}). {START_HINT}",
        )

    async def cache_unavailable(request: Request, exc: Exception):
        from src.app.core.services_status import CACHE_TARGET, START_HINT

        logger.error("Redis unreachable at %s (%s): %s", CACHE_TARGET, type(exc).__name__, exc)
        return _error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "CACHE_UNAVAILABLE",
            f"Redis is unreachable ({CACHE_TARGET}). {START_HINT}",
        )

    for db_error in (
        ConnectionRefusedError,
        socket.gaierror,
        sa_errors.OperationalError,
        sa_errors.InterfaceError,
    ):
        app.add_exception_handler(db_error, database_unavailable)
    for cache_error in (redis_errors.ConnectionError, redis_errors.TimeoutError):
        app.add_exception_handler(cache_error, cache_unavailable)

    @app.exception_handler(OSError)
    async def os_error_handler(request: Request, exc: OSError):
        if "Connect call failed" in str(exc):
            return await database_unavailable(request, exc)
        return await generic_exception_handler(request, exc)

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "INTERNAL_ERROR",
            "An unexpected error occurred",
        )
