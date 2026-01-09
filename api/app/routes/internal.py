import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.dependencies import get_service_token
from app.redis import get_redis

router = APIRouter()


class SendWatchCardRequest(BaseModel):
    tg_user_id: int
    variant_id: int
    title_id: int
    episode_id: int | None = None
    mode: str


class SendVideoRequest(BaseModel):
    tg_user_id: int
    variant_id: int
    priority: str = "normal"


class SendNotificationRequest(BaseModel):
    tg_user_id: int
    title_id: int
    episode_id: int | None = None
    text: str


@router.post("/internal/bot/send_watch_card")
async def send_watch_card(
    payload: SendWatchCardRequest,
    _: None = Depends(get_service_token),
) -> dict:
    redis = get_redis()
    queue = "send_watch_card_queue"
    await redis.rpush(queue, json.dumps(payload.model_dump(), ensure_ascii=False))
    return {"queued": True, "queue": queue}


@router.post("/internal/bot/send_video")
async def send_video(
    payload: SendVideoRequest,
    _: None = Depends(get_service_token),
) -> dict:
    redis = get_redis()
    if payload.priority == "vip":
        queue = "send_video_vip_queue"
    else:
        queue = "send_video_queue"
    await redis.rpush(queue, json.dumps(payload.model_dump(), ensure_ascii=False))
    return {"queued": True, "queue": queue}


@router.post("/internal/bot/send_notification")
async def send_notification(
    payload: SendNotificationRequest,
    _: None = Depends(get_service_token),
) -> dict:
    redis = get_redis()
    queue = "notify_queue"
    await redis.rpush(queue, json.dumps(payload.model_dump(), ensure_ascii=False))
    return {"queued": True, "queue": queue}
