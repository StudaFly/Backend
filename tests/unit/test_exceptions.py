"""
Unit tests for StudaFly business exceptions.
Verify HTTP status codes, error codes and messages for each exception,
as well as the two global handlers: StudaFlyException and generic Exception.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    add_exception_handlers,
)


def test_not_found_error():
    exc = NotFoundError("User")
    assert exc.status_code == 404
    assert exc.code == "NOT_FOUND"
    assert "User" in exc.message


def test_forbidden_error():
    exc = ForbiddenError()
    assert exc.status_code == 403
    assert exc.code == "FORBIDDEN"


def test_conflict_error():
    exc = ConflictError("Email already exists")
    assert exc.status_code == 409
    assert exc.code == "CONFLICT"
    assert "Email" in exc.message


def test_unauthorized_error():
    exc = UnauthorizedError()
    assert exc.status_code == 401
    assert exc.code == "UNAUTHORIZED"


def test_unauthorized_error_custom_message():
    exc = UnauthorizedError("Token expired")
    assert "Token" in exc.message


def test_studafly_exception_handler():
    app = FastAPI()
    add_exception_handlers(app)

    @app.get("/test-error")
    async def raise_error():
        raise NotFoundError("Resource")

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/test-error")
    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "NOT_FOUND"
    assert "Resource" in data["error"]["message"]


def test_generic_exception_handler():
    app = FastAPI()
    add_exception_handlers(app)

    @app.get("/test-generic")
    async def raise_generic():
        raise RuntimeError("Unexpected failure")

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/test-generic")
    assert resp.status_code == 500
    data = resp.json()
    assert data["error"]["code"] == "INTERNAL_ERROR"
