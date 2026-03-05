import redis.asyncio as aioredis

from src.app.core.config import settings

_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


async def get(key: str) -> str | None:
    return await get_redis().get(key)


async def set(key: str, value: str, ttl: int | None = None) -> None:
    await get_redis().set(key, value, ex=ttl)


async def delete(key: str) -> None:
    await get_redis().delete(key)
