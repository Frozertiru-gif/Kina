import json
import os
from typing import Any

from redis.asyncio import Redis

_redis_client: Redis | None = None


def get_redis() -> Redis:
    global _redis_client
    if _redis_client is None:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        _redis_client = Redis.from_url(redis_url, decode_responses=True)
    return _redis_client


async def setnx_with_ttl(key: str, ttl: int) -> bool:
    redis = get_redis()
    result = await redis.set(key, "1", nx=True, ex=ttl)
    return bool(result)


async def json_set(key: str, ttl: int, obj: Any) -> None:
    redis = get_redis()
    payload = json.dumps(obj, ensure_ascii=False)
    await redis.set(key, payload, ex=ttl)
