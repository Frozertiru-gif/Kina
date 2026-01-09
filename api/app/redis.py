from redis.asyncio import Redis

from app.config import get_settings

settings = get_settings()
redis = Redis.from_url(settings.redis_url, decode_responses=True)

QUEUE_SEND_VIDEO = "send_video_queue"
QUEUE_SEND_VIDEO_VIP = "send_video_vip_queue"
QUEUE_NOTIFY = "notify_queue"


async def close_redis() -> None:
    await redis.close()
