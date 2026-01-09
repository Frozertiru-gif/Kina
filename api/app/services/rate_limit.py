import hashlib
from dataclasses import dataclass

from fastapi import status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.redis import get_redis
from app.services.audit import log_audit_event


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after: int


async def check_rate_limit(key: str, limit: int, window_seconds: int) -> RateLimitResult:
    redis = get_redis()
    current = await redis.incr(key)
    if current == 1:
        await redis.expire(key, window_seconds)
        ttl = window_seconds
    else:
        ttl = await redis.ttl(key)
        if ttl is None or ttl < 0:
            ttl = window_seconds
    return RateLimitResult(allowed=current <= limit, retry_after=ttl)


def rate_limit_response(retry_after: int) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"error": "rate_limited", "retry_after": retry_after},
    )


async def register_violation(
    session: AsyncSession,
    tg_user_id: int,
    *,
    threshold: int = 10,
    window_seconds: int = 600,
) -> bool:
    redis = get_redis()
    key = f"abuse:429:{tg_user_id}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window_seconds)
    if count < threshold:
        return False
    result = await session.execute(select(User).where(User.tg_user_id == tg_user_id))
    user = result.scalar_one_or_none()
    if not user or user.is_banned:
        return False
    user.is_banned = True
    user.ban_reason = "auto_abuse"
    await log_audit_event(
        session,
        actor_type="service",
        actor_user_id=None,
        actor_admin_id=None,
        action="user_auto_ban",
        entity_type="user",
        entity_id=user.id,
        metadata_json={"tg_user_id": tg_user_id, "reason": "auto_abuse", "count": count},
    )
    await session.commit()
    return True


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
