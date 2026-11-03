import asyncio
import fnmatch
import os
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from src.app.core.config import settings
from src.app.db.session import get_db
from src.app.main import app
from src.app.services import cache_service

BACKEND_DIR = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or make_url(settings.DATABASE_URL).set(
    database="studafly_test"
).render_as_string(hide_password=False)


def run(coro):
    return asyncio.run(coro)


def make_engine():
    return create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)


@contextmanager
def _database_url(url: str) -> Iterator[None]:
    previous = settings.DATABASE_URL
    settings.DATABASE_URL = url
    try:
        yield
    finally:
        settings.DATABASE_URL = previous


def alembic(action: str, revision: str) -> None:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    with _database_url(TEST_DATABASE_URL):
        getattr(command, action)(config, revision)


async def _reset_database() -> None:
    url = make_url(TEST_DATABASE_URL)
    if not url.database or not url.database.endswith("_test"):
        raise RuntimeError(f"Refusing to wipe {url.database!r}: the name must end with _test")

    server = create_async_engine(
        url.set(database="postgres"), poolclass=NullPool, isolation_level="AUTOCOMMIT"
    )
    try:
        async with server.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
            )
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    finally:
        await server.dispose()

    engine = make_engine()
    try:
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
    finally:
        await engine.dispose()


async def truncate_all() -> None:
    engine = make_engine()
    try:
        async with engine.begin() as conn:
            names = await conn.scalars(
                text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
                )
            )
            tables = ", ".join(f'"{name}"' for name in names)
            if tables:
                await conn.execute(text(f"TRUNCATE {tables} CASCADE"))
    finally:
        await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    try:
        run(_reset_database())
    except (OSError, ConnectionError) as exc:
        if os.environ.get("REQUIRE_TEST_DATABASE") == "1":
            raise
        pytest.skip(f"PostgreSQL not reachable for the DB tests ({exc}) — run `make services`")
    alembic("upgrade", "head")


@pytest.fixture
async def db() -> AsyncIterator[AsyncSession]:
    engine = make_engine()
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            yield session
    finally:
        await engine.dispose()
        await truncate_all()


@pytest.fixture
def fake_cache(monkeypatch) -> dict[str, str]:
    store: dict[str, str] = {}

    async def get(key: str) -> str | None:
        return store.get(key)

    async def set_(key: str, value: str, ttl: int | None = None) -> None:
        store[key] = value

    async def delete(key: str) -> None:
        store.pop(key, None)

    async def delete_pattern(pattern: str) -> None:
        for key in fnmatch.filter(list(store), pattern):
            del store[key]

    monkeypatch.setattr(cache_service, "get", get)
    monkeypatch.setattr(cache_service, "set", set_)
    monkeypatch.setattr(cache_service, "delete", delete)
    monkeypatch.setattr(cache_service, "delete_pattern", delete_pattern)
    return store


@pytest.fixture
async def api(db: AsyncSession, fake_cache) -> AsyncIterator[AsyncClient]:
    engine = make_engine()
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def get_test_db() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = get_test_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test/api/v1"
        ) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        await engine.dispose()
