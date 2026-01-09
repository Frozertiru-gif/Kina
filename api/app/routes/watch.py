import json

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import CurrentUser, get_current_user, get_db_session, is_premium_active
from app.models import MediaVariant
from app.redis import get_redis, json_set, setnx_with_ttl
from app.services.rate_limit import check_rate_limit, rate_limit_response, register_violation

router = APIRouter()


class WatchRequest(BaseModel):
    title_id: int
    episode_id: int | None = None
    audio_id: int
    quality_id: int


class WatchDispatchRequest(BaseModel):
    variant_id: int


@router.post("/watch/request")
async def watch_request(
    payload: WatchRequest,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    throttle_key = f"watchreq:{user.tg_user_id}"
    allowed = await setnx_with_ttl(throttle_key, 2)
    if not allowed:
        await register_violation(session, user.tg_user_id)
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"error": "too_many_requests"},
        )
    rate_key = f"ratelimit:watch_request:{user.tg_user_id}"
    result = await check_rate_limit(rate_key, 20, 60)
    if not result.allowed:
        await register_violation(session, user.tg_user_id)
        return rate_limit_response(result.retry_after)

    variant_query = select(MediaVariant).where(
        MediaVariant.audio_id == payload.audio_id,
        MediaVariant.quality_id == payload.quality_id,
    )
    if payload.episode_id is None:
        variant_query = variant_query.where(
            MediaVariant.title_id == payload.title_id,
            MediaVariant.episode_id.is_(None),
        )
    else:
        variant_query = variant_query.where(MediaVariant.episode_id == payload.episode_id)
    variant_query = variant_query.where(MediaVariant.status.in_(["pending", "ready"]))

    variant_result = await session.execute(variant_query)
    variant = variant_result.scalar_one_or_none()
    if not variant:
        availability_query = select(MediaVariant).where(MediaVariant.title_id == payload.title_id)
        if payload.episode_id is None:
            availability_query = availability_query.where(MediaVariant.episode_id.is_(None))
        else:
            availability_query = availability_query.where(MediaVariant.episode_id == payload.episode_id)
        availability_result = await session.execute(availability_query)
        available_variants = availability_result.scalars().all()
        audio_ids = sorted({item.audio_id for item in available_variants})
        quality_ids = sorted({item.quality_id for item in available_variants})
        variants_payload = [
            {
                "audio_id": item.audio_id,
                "quality_id": item.quality_id,
                "variant_id": item.id,
            }
            for item in available_variants
        ]
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": "variant_not_found",
                "available_audio_ids": audio_ids,
                "available_quality_ids": quality_ids,
                "available_variants": variants_payload,
            },
        )

    premium_active = is_premium_active(user.premium_until)
    mode = "direct" if premium_active else "ad_gate"
    if not premium_active:
        redis = get_redis()
        pass_key = f"ad_pass:{user.tg_user_id}:{variant.id}"
        if await redis.exists(pass_key):
            mode = "direct"
    watchctx_key = f"watchctx:{user.tg_user_id}"
    watch_ctx = {
        "variant_id": variant.id,
        "title_id": payload.title_id,
        "episode_id": payload.episode_id,
    }
    await json_set(watchctx_key, 600, watch_ctx)

    return {
        "mode": mode,
        "variant_id": variant.id,
        "title_id": payload.title_id,
        "episode_id": payload.episode_id,
    }


@router.post("/watch/dispatch")
async def watch_dispatch(
    payload: WatchDispatchRequest,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    redis = get_redis()
    queue = "send_video_vip_queue" if is_premium_active(user.premium_until) else "send_video_queue"
    payload_data = {"tg_user_id": user.tg_user_id, "variant_id": payload.variant_id}
    await redis.rpush(queue, json.dumps(payload_data, ensure_ascii=False))
    return {"queued": True}
