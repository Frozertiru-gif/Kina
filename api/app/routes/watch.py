import json
import logging

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import CurrentUser, get_current_user, get_db_session, is_premium_active
from app.models import MediaVariant
from app.redis import get_redis, json_set, setnx_with_ttl
from app.services.rate_limit import check_rate_limit, rate_limit_response, register_violation
from app.services.watch_resolver import ResolveVariantError, resolve_watch_variant

router = APIRouter()
logger = logging.getLogger("kina.api.watch")


class WatchResolveRequest(BaseModel):
    title_id: int
    episode_id: int | None = None
    audio_id: int | None = None
    quality_id: int | None = None


class WatchResolveResponse(BaseModel):
    variant_id: int
    audio_id: int
    quality_id: int


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

    variant_id = variant.id

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
        "variant_id": variant_id,
        "title_id": payload.title_id,
        "episode_id": payload.episode_id,
    }


@router.post("/watch/resolve", response_model=WatchResolveResponse)
async def watch_resolve(
    payload: WatchResolveRequest,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> WatchResolveResponse:
    try:
        result = await resolve_watch_variant(
            session,
            user_id=user.id,
            title_id=payload.title_id,
            episode_id=payload.episode_id,
            audio_id=payload.audio_id,
            quality_id=payload.quality_id,
        )
    except ResolveVariantError as exc:
        logger.info(
            "watch resolve failed",
            extra={
                "action": "watch_resolve_no_ready_with_file",
                "user_id": user.id,
                "title_id": payload.title_id,
                "episode_id": payload.episode_id,
                "counts": exc.payload.counts,
            },
        )
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": exc.payload.error,
                "counts": exc.payload.counts,
                "available_audio_ids": exc.payload.available_audio_ids,
                "available_quality_ids": exc.payload.available_quality_ids,
                "available_variants": exc.payload.available_variants,
            },
        )
    return WatchResolveResponse(
        variant_id=result.variant_id,
        audio_id=result.audio_id,
        quality_id=result.quality_id,
    )


@router.post("/watch/dispatch")
async def watch_dispatch(
    payload: WatchDispatchRequest,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    redis = get_redis()
    premium_active = is_premium_active(user.premium_until)
    if not premium_active:
        pass_key = f"ad_pass:{user.tg_user_id}:{payload.variant_id}"
        if not await redis.exists(pass_key):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"error": "ad_required"},
            )
    dedupe_key = f"vsend:{user.tg_user_id}:{payload.variant_id}"
    if not await setnx_with_ttl(dedupe_key, 120):
        return {"queued": False, "deduped": True}
    queue = "send_video_vip_queue" if premium_active else "send_video_queue"
    payload_data = {"tg_user_id": user.tg_user_id, "variant_id": payload.variant_id}
    await redis.rpush(queue, json.dumps(payload_data, ensure_ascii=False))
    return {"queued": True}
