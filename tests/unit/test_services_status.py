"""Unavailable PostgreSQL / Redis must give an explicit 503, not a 500 traceback."""

import redis.exceptions as redis_errors
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import exc as sa_errors
from src.app.core.exceptions import add_exception_handlers
from src.app.core.services_status import target


def _client_raising(exc: Exception) -> TestClient:
    app = FastAPI()
    add_exception_handlers(app)

    @app.get("/boom")
    async def boom():
        raise exc

    return TestClient(app, raise_server_exceptions=False)


def test_refused_database_connection_gives_503():
    r = _client_raising(ConnectionRefusedError(61, "Connection refused")).get("/boom")
    assert r.status_code == 503
    error = r.json()["error"]
    assert error["code"] == "DATABASE_UNAVAILABLE"
    assert "make services" in error["message"]


def test_sqlalchemy_operational_error_gives_503():
    exc = sa_errors.OperationalError("SELECT 1", {}, Exception("database does not exist"))
    r = _client_raising(exc).get("/boom")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "DATABASE_UNAVAILABLE"


def test_redis_down_gives_503():
    r = _client_raising(redis_errors.ConnectionError("Error 61 connecting")).get("/boom")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "CACHE_UNAVAILABLE"


def test_other_errors_stay_500():
    r = _client_raising(RuntimeError("bug")).get("/boom")
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "INTERNAL_ERROR"


def test_target_never_exposes_credentials():
    assert (
        target("postgresql+asyncpg://studafly:secret@localhost:5432/studafly") == "localhost:5432"
    )
    assert target("redis://localhost:6379/0") == "localhost:6379"


def test_refused_connection_without_uvloop_gives_503():
    exc = OSError(
        "Multiple exceptions: [Errno 61] Connect call failed ('::1', 5432, 0, 0), "
        "[Errno 61] Connect call failed ('127.0.0.1', 5432)"
    )
    r = _client_raising(exc).get("/boom")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "DATABASE_UNAVAILABLE"


def test_unrelated_os_error_stays_500():
    r = _client_raising(OSError("disk full")).get("/boom")
    assert r.status_code == 500
