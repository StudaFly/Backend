import hashlib
import json

from src.app.core.config import settings
from src.app.services import cache_service


def _make_key(prefix: str, params: dict) -> str:
    serialized = json.dumps(params, sort_keys=True)
    digest = hashlib.sha256(serialized.encode()).hexdigest()[:16]
    return f"ai:{prefix}:{digest}"


async def get_cached(prefix: str, params: dict) -> str | None:
    key = _make_key(prefix, params)
    return await cache_service.get(key)


async def set_cached(prefix: str, params: dict, value: str) -> None:
    key = _make_key(prefix, params)
    await cache_service.set(key, value, ttl=settings.AI_CACHE_TTL)
