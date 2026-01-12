import json
import logging
import os
import re
from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import (
    _ensure_not_banned,
    _issue_access_token,
    _parse_init_data,
    _validate_init_data,
    get_db_session,
)
from app.models import UserPremium
from app.dependencies import _get_dev_user_id, _is_dev_bypass_allowed, _upsert_user
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
    access_token: str
    token_type: str
    expires_in: int


async def _get_premium_until(session: AsyncSession, user_id: int) -> Any | None:
    result = await session.execute(
        select(UserPremium.premium_until).where(UserPremium.user_id == user_id)
    )
    return result.scalar_one_or_none()


@router.post("/auth/webapp", response_model=WebAppAuthResponse)
async def auth_webapp(
    request: Request,
    payload: WebAppAuthRequest = Body(...),
    x_dev_user_id: str | None = Header(default=None, alias="X-Dev-User-Id"),
    x_init_data: str | None = Header(default=None, alias="X-Init-Data"),
    session: AsyncSession = Depends(get_db_session),
) -> WebAppAuthResponse:
    init_data = payload.initData or x_init_data
    referral_code = payload.ref
    if _is_webapp_debug_enabled():
        body_bytes = await request.body() if request else b""
        init_data_source = "body" if payload.initData else "header" if x_init_data else "missing"
        init_data_preview = init_data or ""
        masked_preview = re.sub(r"(user=)[^&]*", r"\1<redacted>", init_data_preview)
        masked_preview = re.sub(r"(hash=)[^&]*", r"\1<redacted>", masked_preview)
        preview_start = masked_preview[:80]
        preview_end = masked_preview[-80:] if len(masked_preview) > 80 else masked_preview
        logger.info(
            "auth webapp debug",
            extra={
                "action": "auth_webapp_debug",
                "init_data_source": init_data_source,
                "init_data_len": len(init_data or ""),
                "init_data_preview_start": preview_start,
                "init_data_preview_end": preview_end,
                "user_agent": request.headers.get("user-agent") if request else None,
                "x_forwarded_for": request.headers.get("x-forwarded-for") if request else None,
                "x_request_id": request.headers.get("x-request-id") if request else None,
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
        access_token, expires_in = _issue_access_token(user)
        return WebAppAuthResponse(
            id=user.id,
            tg_user_id=user.tg_user_id,
            username=user.username,
            first_name=user.first_name,
            premium_until=premium_until,
            access_token=access_token,
            token_type="Bearer",
            expires_in=expires_in,
        )

    if not init_data:
        detail = "init_data_required" if _is_webapp_debug_enabled() else "unauthorized"
        if _is_webapp_debug_enabled():
            logger.info(
                "auth webapp rejected",
                extra={
                    "action": "auth_webapp_rejected",
                    "detail": detail,
                    "rejection_reason": "parse error",
                    "status_code": status.HTTP_401_UNAUTHORIZED,
                },
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="bot_token_missing")
    try:
        parsed = (
            _validate_init_data(init_data, bot_token)
            if _is_webapp_strict()
            else _parse_init_data(init_data)
        )
    except HTTPException as exc:
        if _is_webapp_debug_enabled():
            if exc.detail == "init_data_expired":
                rejection_reason = "expired"
            elif exc.detail in {"bad_hash_format", "clock_skew", "init_data_invalid"}:
                rejection_reason = "invalid hash"
            else:
                rejection_reason = "parse error"
            logger.info(
                "auth webapp rejected",
                extra={
                    "action": "auth_webapp_rejected",
                    "detail": exc.detail,
                    "rejection_reason": rejection_reason,
                    "status_code": exc.status_code,
                },
            )
            raise
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unauthorized",
        ) from exc
    raw_user = parsed.get("user")
    if not raw_user:
        detail = "init_data_user_missing" if _is_webapp_debug_enabled() else "unauthorized"
        if _is_webapp_debug_enabled():
            logger.info(
                "auth webapp rejected",
                extra={
                    "action": "auth_webapp_rejected",
                    "detail": detail,
                    "rejection_reason": "parse error",
                    "status_code": status.HTTP_401_UNAUTHORIZED,
                },
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)
    if _is_webapp_debug_enabled():
        logger.info(
            "auth webapp parsed",
            extra={
                "action": "auth_webapp_parsed",
                "parsed_keys": sorted(parsed.keys()),
                "has_user": bool(raw_user),
                "has_hash": "hash" in parsed,
                "auth_date": parsed.get("auth_date"),
            },
        )
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
    access_token, expires_in = _issue_access_token(user)
    return WebAppAuthResponse(
        id=user.id,
        tg_user_id=user.tg_user_id,
        username=user.username,
        first_name=user.first_name,
        premium_until=premium_until,
        access_token=access_token,
        token_type="Bearer",
        expires_in=expires_in,
    )
