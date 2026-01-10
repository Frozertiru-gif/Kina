import json
import logging
import os
from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import _ensure_not_banned, _parse_init_data, get_db_session
from app.models import UserPremium
from app.dependencies import _get_dev_user_id, _is_dev_bypass_allowed, _upsert_user, _validate_init_data
from app.services.rate_limit import rate_limit_response, register_violation
from app.services.referrals import (
    ReferralRateLimitError,
    apply_referral_code,
    get_referral_reward_days,
)

router = APIRouter()
logger = logging.getLogger("kina.api")


def _is_webapp_debug_enabled() -> bool:
    return os.getenv("AUTH_WEBAPP_DEBUG", "0") == "1"


def _is_webapp_strict() -> bool:
    return os.getenv("AUTH_WEBAPP_STRICT", "1") != "0"


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
    x_init_data: str | None = Header(default=None, alias="X-Init-Data"),
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> WebAppAuthResponse:
    init_data = payload.initData or x_init_data
    referral_code = payload.ref
    if _is_webapp_debug_enabled():
        body_bytes = await request.body() if request else b""
        init_data_source = "body" if payload.initData else "header" if x_init_data else "missing"
        init_data_preview = init_data[:120] if init_data else ""
        logger.info(
            "auth webapp debug",
            extra={
                "action": "auth_webapp_debug",
                "init_data_source": init_data_source,
                "init_data_len": len(init_data or ""),
                "init_data_preview": init_data_preview,
                "content_type": request.headers.get("content-type") if request else None,
                "body_len": len(body_bytes),
                "header_init_data_len": len(x_init_data or ""),
            },
        )
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
    parsed = (
        _validate_init_data(init_data, bot_token)
        if _is_webapp_strict()
        else _parse_init_data(init_data)
    )
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
