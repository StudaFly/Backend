"""Reachability of the services the API depends on (PostgreSQL, Redis).

Used at startup (clear log line instead of a first-request traceback), by
GET /api/v1/health and by the 503 error handlers.
"""

import logging
from urllib.parse import urlsplit

from sqlalchemy import text

from src.app.core.config import settings

logger = logging.getLogger(__name__)


def target(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.hostname}:{parts.port}" if parts.port else str(parts.hostname)


DATABASE_TARGET = target(settings.DATABASE_URL)
CACHE_TARGET = target(settings.REDIS_URL)
START_HINT = "Start it with `make services` in backend/ (or `make docker-up` for the full stack)."


async def check_database() -> bool:
    from src.app.db.session import engine

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def check_cache() -> bool:
    from src.app.services.cache_service import get_redis

    try:
        return bool(await get_redis().ping())
    except Exception:
        return False


async def log_services_status() -> None:
    if not await check_database():
        logger.error("PostgreSQL unreachable at %s. %s", DATABASE_TARGET, START_HINT)
    if not await check_cache():
        logger.error("Redis unreachable at %s. %s", CACHE_TARGET, START_HINT)
