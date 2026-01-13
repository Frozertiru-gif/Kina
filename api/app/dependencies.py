import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, unquote

import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models import User, UserPremium
from app.services.rate_limit import check_rate_limit, hash_token

logger = logging.getLogger("kina.api")


class CurrentUser(BaseModel):
    id: int
    tg_user_id: int
    username: str | None
    first_name: str | None
    premium_until: datetime | None


class BannedUserError(Exception):
    pass


async def get_db_session() -> AsyncSession:
    async with SessionLocal() as session:
        yield session


def _is_dev_bypass_allowed() -> bool:
    environment = os.getenv("ENVIRONMENT")
    return environment in {"local", "development", "dev"}


def _get_dev_user_id(dev_user_id: str | None) -> int:
    if dev_user_id:
        return int(dev_user_id)
    env_user_id = os.getenv("DEV_TG_USER_ID")
    if env_user_id:
        return int(env_user_id)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="dev_user_id_required",
    )


def _is_webapp_debug_enabled() -> bool:
    return os.getenv("AUTH_WEBAPP_DEBUG", "0") == "1"


def _get_bot_token() -> str:
    token = (
        os.getenv("BOT_TOKEN")
        or os.getenv("TELEGRAM_BOT_TOKEN")
        or os.getenv("WEBAPP_BOT_TOKEN")
    )
    if not token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="bot_token_missing",
        )
    return token


def _extract_tg_webapp_data(init_data: str) -> str:
    normalized = init_data.strip()
    if normalized.startswith("?") or normalized.startswith("#"):
        normalized = normalized[1:]
    if "tgWebAppData=" not in normalized:
        return normalized
    for part in normalized.split("&"):
        if not part:
            continue
        key, _, value = part.partition("=")
        if key == "tgWebAppData":
            return unquote(value)
    return normalized


def _validate_init_data(init_data: str, bot_token: str, *, debug: bool = False) -> dict[str, Any]:
    has_hash = False
    has_auth_date = False
    has_user = False

    def _log_failure(reason: str) -> None:
        if debug and _is_webapp_debug_enabled():
            logger.info(
                "init data validation failed",
                extra={
                    "action": "init_data_validation_failed",
                    "reason": reason,
                    "init_data_len": len(init_data),
                    "has_hash": has_hash,
                    "has_auth_date": has_auth_date,
                    "has_user": has_user,
                },
            )

    normalized = _extract_tg_webapp_data(init_data)
    try:
        pairs = parse_qsl(normalized, strict_parsing=True, keep_blank_values=True)
    except ValueError as exc:
        _log_failure("parse_error")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="init_data_invalid",
        ) from exc

    data: dict[str, str] = {}
    hash_from_tg: str | None = None
    for key, value in pairs:
        if key == "hash":
            hash_from_tg = value
            has_hash = True
            continue
        data[key] = value
        if key == "auth_date":
            has_auth_date = True
        if key == "user":
            has_user = True

    if not hash_from_tg:
        _log_failure("missing_hash")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="init_data_invalid",
        )

    data_check_string = "\n".join(f"{key}={data[key]}" for key in sorted(data))
    secret_key = hmac.new(
        b"WebAppData",
        bot_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(calculated_hash, hash_from_tg):
        _log_failure("hash_mismatch")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="init_data_invalid",
        )

    auth_date_raw = data.get("auth_date")
    if not auth_date_raw:
        _log_failure("missing_auth_date")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="init_data_invalid",
        )
    try:
        auth_date = int(auth_date_raw)
    except (TypeError, ValueError) as exc:
        _log_failure("parse_error")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="init_data_invalid",
        ) from exc

    now_ts = int(datetime.now(timezone.utc).timestamp())
    max_age = int(os.getenv("AUTH_WEBAPP_MAX_AGE_SECONDS", "86400"))
    clock_skew = int(os.getenv("AUTH_WEBAPP_CLOCK_SKEW_SECONDS", "120"))
    if auth_date > now_ts + clock_skew:
        _log_failure("clock_skew")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="clock_skew",
        )
    if now_ts - auth_date > max_age:
        _log_failure("expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="init_data_expired",
        )

    return data


def _get_jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET") or os.getenv("BOT_TOKEN")
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="jwt_secret_missing",
        )
    return secret


def _get_jwt_ttl_seconds() -> int:
    ttl = int(os.getenv("JWT_TTL_SECONDS", "43200"))
    min_ttl = 21600
    max_ttl = 86400
    return max(min_ttl, min(max_ttl, ttl))


def _issue_access_token(user: User) -> tuple[str, int]:
    ttl = _get_jwt_ttl_seconds()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "tg_user_id": user.tg_user_id,
        "iat": int(now.timestamp()),
        "exp": int((now.timestamp() + ttl)),
    }
    token = jwt.encode(payload, _get_jwt_secret(), algorithm="HS256")
    return token, ttl


def _decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, _get_jwt_secret(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token_expired",
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token_invalid",
        ) from exc


async def _upsert_user(
    session: AsyncSession,
    tg_user_id: int,
    username: str | None,
    first_name: str | None,
    language_code: str | None,
) -> User:
    result = await session.execute(select(User).where(User.tg_user_id == tg_user_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            tg_user_id=tg_user_id,
            username=username,
            first_name=first_name,
            language_code=language_code,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user

    user.username = username
    user.first_name = first_name
    user.language_code = language_code
    await session.commit()
    await session.refresh(user)
    return user


async def _get_premium_until(session: AsyncSession, user_id: int) -> datetime | None:
    result = await session.execute(
        select(UserPremium.premium_until).where(UserPremium.user_id == user_id)
    )
    return result.scalar_one_or_none()


def _ensure_not_banned(user: User) -> None:
    if user.is_banned:
        raise BannedUserError()


async def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_init_data: str | None = Header(default=None, alias="X-Init-Data"),
    x_dev_user_id: str | None = Header(default=None, alias="X-Dev-User-Id"),
    session: AsyncSession = Depends(get_db_session),
) -> CurrentUser:
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="token_invalid",
            )
        payload = _decode_access_token(token)
        user_id_raw = payload.get("sub")
        if not user_id_raw:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="token_user_missing",
            )
        result = await session.execute(select(User).where(User.id == int(user_id_raw)))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="token_user_missing",
            )
        premium_until = await _get_premium_until(session, user.id)
        _ensure_not_banned(user)
        request.state.tg_user_id = user.tg_user_id
        return CurrentUser(
            id=user.id,
            tg_user_id=user.tg_user_id,
            username=user.username,
            first_name=user.first_name,
            premium_until=premium_until,
        )

    if _is_dev_bypass_allowed():
        tg_user_id = _get_dev_user_id(x_dev_user_id)
        user = await _upsert_user(session, tg_user_id, None, None, None)
        premium_until = await _get_premium_until(session, user.id)
        _ensure_not_banned(user)
        request.state.tg_user_id = user.tg_user_id
        return CurrentUser(
            id=user.id,
            tg_user_id=user.tg_user_id,
            username=user.username,
            first_name=user.first_name,
            premium_until=premium_until,
        )

    if not x_init_data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token_missing")
    bot_token = _get_bot_token()
    parsed = _validate_init_data(x_init_data, bot_token)
    raw_user = parsed.get("user")
    if not raw_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="init_data_user_missing")
    user_payload = json.loads(raw_user)
    tg_user_id = int(user_payload["id"])
    user = await _upsert_user(
        session,
        tg_user_id,
        user_payload.get("username"),
        user_payload.get("first_name"),
        user_payload.get("language_code"),
    )
    premium_until = await _get_premium_until(session, user.id)
    _ensure_not_banned(user)
    request.state.tg_user_id = user.tg_user_id
    return CurrentUser(
        id=user.id,
        tg_user_id=user.tg_user_id,
        username=user.username,
        first_name=user.first_name,
        premium_until=premium_until,
    )


def is_premium_active(premium_until: datetime | None) -> bool:
    if not premium_until:
        return False
    return premium_until > datetime.now(timezone.utc)


async def _rate_limit_token(token: str, limit: int) -> None:
    key = f"ratelimit:token:{hash_token(token)}"
    result = await check_rate_limit(key, limit, 60)
    if not result.allowed:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate_limited")


async def get_service_token(
    x_service_token: str | None = Header(default=None, alias="X-Service-Token"),
) -> None:
    expected = os.getenv("SERVICE_TOKEN")
    if not expected or x_service_token != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_service_token")
    await _rate_limit_token(expected, 120)


def _parse_admin_allowlist(raw: str | None) -> set[int]:
    if not raw:
        return set()
    ids: set[int] = set()
    for item in raw.split(","):
        value = item.strip()
        if not value:
            continue
        try:
            ids.add(int(value))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="invalid_admin_allowlist",
            ) from exc
    return ids


async def get_admin_token(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    x_admin_user_id: str | None = Header(default=None, alias="X-Admin-User-Id"),
) -> dict:
    expected = os.getenv("ADMIN_SERVICE_TOKEN") or os.getenv("SERVICE_TOKEN")
    if not expected or x_admin_token != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_admin_token")
    await _rate_limit_token(expected, 60)
    allowlist = _parse_admin_allowlist(os.getenv("ADMIN_ALLOWLIST"))
    if allowlist:
        if not x_admin_user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="admin_user_id_required",
            )
        try:
            admin_id = int(x_admin_user_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="admin_user_id_invalid",
            ) from exc
        if admin_id not in allowlist:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="admin_user_not_allowed",
            )
        return {"tg_user_id": admin_id}
    return {"tg_user_id": None}
