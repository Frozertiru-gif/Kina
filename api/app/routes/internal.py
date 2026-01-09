import json
import os

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db_session, get_service_token, is_premium_active, _upsert_user
from app.models import (
    Favorite,
    MediaVariant,
    Subscription,
    Title,
    TitleType,
    UploadJob,
    User,
    UserPremium,
)
from app.redis import get_redis, json_set, setnx_with_ttl
from app.services.rate_limit import rate_limit_response, register_violation
from app.services.referrals import (
    ReferralRateLimitError,
    apply_referral_code,
    ensure_referral_code,
    get_referral_reward_days,
)

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


class ToggleFavoriteRequest(BaseModel):
    tg_user_id: int
    title_id: int


class ToggleSubscriptionRequest(BaseModel):
    tg_user_id: int
    title_id: int


class WatchRequest(BaseModel):
    tg_user_id: int
    title_id: int
    episode_id: int | None = None
    audio_id: int
    quality_id: int


class RetryUploadJobRequest(BaseModel):
    job_id: int


class ReferralApplyRequest(BaseModel):
    tg_user_id: int
    code: str
    username: str | None = None
    first_name: str | None = None
    language_code: str | None = None


class ReferralCodeRequest(BaseModel):
    tg_user_id: int
    username: str | None = None
    first_name: str | None = None
    language_code: str | None = None


async def _count_keys(redis, pattern: str) -> int:
    total = 0
    cursor = 0
    while True:
        cursor, keys = await redis.scan(cursor=cursor, match=pattern, count=200)
        total += len(keys)
        if cursor == 0:
            break
    return total


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


@router.post("/internal/bot/favorites/toggle")
async def toggle_favorite_internal(
    payload: ToggleFavoriteRequest,
    _: None = Depends(get_service_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    user = await _get_or_create_user(session, payload.tg_user_id)
    result = await session.execute(
        select(Favorite).where(
            Favorite.user_id == user.id,
            Favorite.title_id == payload.title_id,
        )
    )
    favorite = result.scalar_one_or_none()
    if favorite:
        await session.delete(favorite)
        await session.commit()
        return {"title_id": payload.title_id, "favorited": False}

    title_result = await session.execute(select(Title).where(Title.id == payload.title_id))
    title = title_result.scalar_one_or_none()
    if not title:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="title_not_found")

    session.add(Favorite(user_id=user.id, title_id=payload.title_id))
    await session.commit()
    return {"title_id": payload.title_id, "favorited": True}


@router.post("/internal/bot/subscriptions/toggle")
async def toggle_subscription_internal(
    payload: ToggleSubscriptionRequest,
    _: None = Depends(get_service_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    return await _toggle_subscription(session, payload.tg_user_id, payload.title_id)


@router.post("/internal/user/subscription_toggle")
async def toggle_subscription_internal_user(
    payload: ToggleSubscriptionRequest,
    _: None = Depends(get_service_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    return await _toggle_subscription(session, payload.tg_user_id, payload.title_id)


@router.post("/internal/bot/watch/request")
async def watch_request_internal(
    payload: WatchRequest,
    _: None = Depends(get_service_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    throttle_key = f"watchreq:{payload.tg_user_id}"
    allowed = await setnx_with_ttl(throttle_key, 2)
    if not allowed:
        return {"error": "too_many_requests"}

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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="variant_not_found")

    premium_until = await _get_premium_until(session, payload.tg_user_id)
    premium_active = is_premium_active(premium_until)
    mode = "direct" if premium_active else "ad_gate"
    if not premium_active:
        redis = get_redis()
        pass_key = f"ad_pass:{payload.tg_user_id}:{variant.id}"
        if await redis.exists(pass_key):
            mode = "direct"
    watchctx_key = f"watchctx:{payload.tg_user_id}"
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


@router.post("/internal/uploader/retry_job")
async def retry_upload_job(
    payload: RetryUploadJobRequest,
    _: None = Depends(get_service_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await session.execute(select(UploadJob).where(UploadJob.id == payload.job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job_not_found")
    job.status = "queued"
    job.last_error = None
    job.attempts = 0
    variant = await session.get(MediaVariant, job.variant_id)
    if variant:
        variant.status = "uploading"
        variant.error = None
    await session.commit()
    return {"job_id": job.id, "status": job.status}


@router.get("/internal/uploader/jobs")
async def list_upload_jobs(
    status: str | None = Query(default=None, max_length=50),
    limit: int = Query(default=50, ge=1, le=200),
    _: None = Depends(get_service_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    query = select(UploadJob).order_by(UploadJob.id.desc()).limit(limit)
    if status:
        query = query.where(UploadJob.status == status)
    result = await session.execute(query)
    jobs = result.scalars().all()
    return {
        "items": [
            {
                "id": job.id,
                "variant_id": job.variant_id,
                "status": job.status,
                "attempts": job.attempts,
                "local_path": job.local_path,
                "last_error": job.last_error,
            }
            for job in jobs
        ]
    }


@router.post("/internal/uploader/rescan")
async def uploader_rescan(_: None = Depends(get_service_token)) -> dict:
    redis = get_redis()
    await redis.rpush("uploader_control_queue", json.dumps({"action": "rescan"}))
    return {"queued": True}


@router.post("/internal/referral/apply")
async def apply_referral_internal(
    payload: ReferralApplyRequest,
    _: None = Depends(get_service_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    user = await _upsert_user(
        session,
        payload.tg_user_id,
        payload.username,
        payload.first_name,
        payload.language_code,
    )
    try:
        applied = await apply_referral_code(
            session,
            user,
            payload.code,
            get_referral_reward_days(),
            actor_type="service",
        )
    except ReferralRateLimitError as exc:
        await register_violation(session, payload.tg_user_id)
        return rate_limit_response(exc.retry_after)
    return {"applied": applied}


@router.post("/internal/referral/code")
async def get_referral_code_internal(
    payload: ReferralCodeRequest,
    _: None = Depends(get_service_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    user = await _upsert_user(
        session,
        payload.tg_user_id,
        payload.username,
        payload.first_name,
        payload.language_code,
    )
    code = await ensure_referral_code(session, user.id)
    base_url = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    link = f"{base_url}?startapp=ref_{code}" if base_url else f"?startapp=ref_{code}"
    return {"code": code, "link": link}


@router.get("/internal/metrics")
async def get_metrics(
    _: None = Depends(get_service_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    redis = get_redis()
    queues = [
        "send_watch_card_queue",
        "send_video_queue",
        "send_video_vip_queue",
        "notify_queue",
        "uploader_control_queue",
    ]
    queue_lengths = {queue: await redis.llen(queue) for queue in queues}

    upload_statuses = ["queued", "uploading", "failed", "done"]
    upload_counts = {}
    for status_name in upload_statuses:
        result = await session.execute(
            select(func.count()).select_from(UploadJob).where(UploadJob.status == status_name)
        )
        upload_counts[status_name] = result.scalar_one()

    variant_statuses = ["pending", "ready", "failed"]
    variant_counts = {}
    for status_name in variant_statuses:
        result = await session.execute(
            select(func.count()).select_from(MediaVariant).where(MediaVariant.status == status_name)
        )
        variant_counts[status_name] = result.scalar_one()

    users_total = await session.execute(select(func.count()).select_from(User))
    users_banned = await session.execute(
        select(func.count()).select_from(User).where(User.is_banned.is_(True))
    )

    ads_passes = await _count_keys(redis, "ad_pass:*")

    return {
        "queue_lengths": queue_lengths,
        "upload_jobs": upload_counts,
        "variants": variant_counts,
        "users": {"total": users_total.scalar_one(), "banned": users_banned.scalar_one()},
        "ads": {"passes_active_estimate": ads_passes},
    }


async def _toggle_subscription(
    session: AsyncSession,
    tg_user_id: int,
    title_id: int,
) -> dict:
    user = await _get_or_create_user(session, tg_user_id)
    title_result = await session.execute(select(Title).where(Title.id == title_id))
    title = title_result.scalar_one_or_none()
    if not title:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="title_not_found")
    if title.type != TitleType.SERIES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="series_only")
    result = await session.execute(
        select(Subscription).where(
            Subscription.user_id == user.id,
            Subscription.title_id == title_id,
        )
    )
    subscription = result.scalar_one_or_none()
    if subscription:
        subscription.enabled = not subscription.enabled
        await session.commit()
        return {"title_id": title_id, "enabled": subscription.enabled}

    session.add(Subscription(user_id=user.id, title_id=title_id, enabled=True))
    await session.commit()
    return {"title_id": title_id, "enabled": True}


async def _get_or_create_user(session: AsyncSession, tg_user_id: int) -> User:
    result = await session.execute(select(User).where(User.tg_user_id == tg_user_id))
    user = result.scalar_one_or_none()
    if user:
        return user
    user = User(tg_user_id=tg_user_id)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _get_premium_until(session: AsyncSession, tg_user_id: int):
    result = await session.execute(
        select(UserPremium)
        .join(User, UserPremium.user_id == User.id)
        .where(User.tg_user_id == tg_user_id)
    )
    record = result.scalar_one_or_none()
    return record.premium_until if record else None
