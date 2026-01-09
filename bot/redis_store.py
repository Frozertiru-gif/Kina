from redis.asyncio import Redis

from bot.config import get_settings

settings = get_settings()
redis = Redis.from_url(settings.redis_url, decode_responses=True)

QUEUE_SEND_VIDEO = "send_video_queue"
QUEUE_SEND_VIDEO_VIP = "send_video_vip_queue"
QUEUE_NOTIFY = "notify_queue"

AD_NONCE_PREFIX = "ad:nonce:"
AD_PASS_PREFIX = "ad:pass:"


async def set_ad_nonce(user_id: int, nonce: str, ttl_seconds: int) -> None:
    await redis.set(f"{AD_NONCE_PREFIX}{user_id}", nonce, ex=ttl_seconds)


async def set_ad_pass(user_id: int, token: str, ttl_seconds: int) -> None:
    await redis.set(f"{AD_PASS_PREFIX}{user_id}", token, ex=ttl_seconds)


async def get_ad_nonce(user_id: int) -> str | None:
    return await redis.get(f"{AD_NONCE_PREFIX}{user_id}")


async def get_ad_pass(user_id: int) -> str | None:
    return await redis.get(f"{AD_PASS_PREFIX}{user_id}")


async def rate_limit(key: str, ttl_seconds: int) -> bool:
    """Return True if allowed, False if limited."""
    token = await redis.set(key, "1", ex=ttl_seconds, nx=True)
    return token is True


async def close_redis() -> None:
    await redis.close()
