import json
import os
from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import _ensure_not_banned, get_db_session
from app.models import UserPremium
from app.dependencies import _get_dev_user_id, _is_dev_bypass_allowed, _upsert_user, _validate_init_data
from app.services.rate_limit import rate_limit_response, register_violation
from app.services.referrals import (
    ReferralRateLimitError,
    apply_referral_code,
    get_referral_reward_days,
)

router = APIRouter()


class WebAppAuthRequest(BaseModel):
    initData: str | None = None
    ref: str | None = None


class WebAppAuthResponse(BaseModel):
    id: int
    tg_user_id: int
    username: str | None
    first_name: str | None
    premium_until: Any | None


async def _get_premium_until(session: AsyncSession, user_id: int) -> Any | None:
    result = await session.execute(
        select(UserPremium.premium_until).where(UserPremium.user_id == user_id)
    )
    return result.scalar_one_or_none()


@router.post("/auth/webapp", response_model=WebAppAuthResponse)
async def auth_webapp(
    payload: WebAppAuthRequest = Body(...),
    x_dev_user_id: str | None = Header(default=None, alias="X-Dev-User-Id"),
    session: AsyncSession = Depends(get_db_session),
) -> WebAppAuthResponse:
    init_data = payload.initData
    referral_code = payload.ref
    if _is_dev_bypass_allowed() and not init_data:
        tg_user_id = _get_dev_user_id(x_dev_user_id)
        user = await _upsert_user(session, tg_user_id, None, None, None)
        _ensure_not_banned(user)
        if referral_code:
            try:
                await apply_referral_code(
                    session,
                    user,
                    referral_code,
                    get_referral_reward_days(),
                )
            except ReferralRateLimitError as exc:
                await register_violation(session, tg_user_id)
                return rate_limit_response(exc.retry_after)
        premium_until = await _get_premium_until(session, user.id)
        return WebAppAuthResponse(
            id=user.id,
            tg_user_id=user.tg_user_id,
            username=user.username,
            first_name=user.first_name,
            premium_until=premium_until,
        )

    if not init_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="init_data_required")
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="bot_token_missing")
    parsed = _validate_init_data(init_data, bot_token)
    raw_user = parsed.get("user")
    if not raw_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="init_data_user_missing")
    user_payload = json.loads(raw_user)
    tg_user_id = int(user_payload["id"])
    user = await _upsert_user(
        session,
        tg_user_id,
        user_payload.get("username"),
        user_payload.get("first_name"),
        user_payload.get("language_code"),
    )
    _ensure_not_banned(user)
    if referral_code:
        try:
            await apply_referral_code(
                session,
                user,
                referral_code,
                get_referral_reward_days(),
            )
        except ReferralRateLimitError as exc:
            await register_violation(session, tg_user_id)
            return rate_limit_response(exc.retry_after)
    premium_until = await _get_premium_until(session, user.id)
    return WebAppAuthResponse(
        id=user.id,
        tg_user_id=user.tg_user_id,
        username=user.username,
        first_name=user.first_name,
        premium_until=premium_until,
    )
