import hashlib
import hmac
import json
import os
import re
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


def _parse_init_data(init_data: str, *, treat_plus_as_space: bool = True) -> dict[str, Any]:
    if treat_plus_as_space:
        return dict(parse_qsl(init_data, strict_parsing=False, keep_blank_values=True))
    pairs: list[tuple[str, str]] = []
    for chunk in init_data.split("&"):
        if not chunk:
            continue
        key, _, value = chunk.partition("=")
        pairs.append((unquote(key), unquote(value)))
    return dict(pairs)


def _normalize_init_data_candidates(init_data: str) -> list[str]:
    normalized = init_data.strip()
    if normalized.startswith("?") or normalized.startswith("#"):
        normalized = normalized[1:]
    if "tgWebAppData=" in normalized:
        for part in normalized.split("&"):
            if not part:
                continue
            if part.startswith("tgWebAppData="):
                normalized = unquote(part.split("=", 1)[1])
                break
    if "%3D" in normalized or "%26" in normalized:
        normalized = unquote(normalized)
    candidates = [normalized]
    if " " in normalized and "+" not in normalized:
        candidates.append(normalized.replace(" ", "+"))
    deduped: list[str] = []
    for item in candidates:
        if item not in deduped:
            deduped.append(item)
    return deduped


def _validate_init_data(init_data: str, bot_token: str) -> dict[str, Any]:
    variants: list[dict[str, Any]] = []
    for candidate in _normalize_init_data_candidates(init_data):
        variants.append(_parse_init_data(candidate))
        variants.append(_parse_init_data(candidate, treat_plus_as_space=False))

    has_hash = False
    bad_hash_format = False
    for parsed in variants:
        provided_hash = parsed.get("hash")
        if provided_hash is None:
            continue
        has_hash = True
        if not re.fullmatch(r"[0-9a-f]{64}", str(provided_hash)):
            bad_hash_format = True
            continue
        data_check_string = "\n".join(
            f"{key}={value}" for key, value in sorted(parsed.items()) if key != "hash"
        )
        secret = hashlib.sha256(bot_token.encode("utf-8")).digest()
        calculated_hash = hmac.new(
            secret, data_check_string.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(calculated_hash, provided_hash):
            continue
        auth_date_raw = parsed.get("auth_date")
        if not auth_date_raw:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="init_data_invalid",
            )
        try:
            auth_date = int(auth_date_raw)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="init_data_invalid",
            ) from exc
        now_ts = int(datetime.now(timezone.utc).timestamp())
        max_age = int(os.getenv("AUTH_WEBAPP_MAX_AGE_SECONDS", "86400"))
        clock_skew = int(os.getenv("AUTH_WEBAPP_CLOCK_SKEW_SECONDS", "120"))
        if auth_date > now_ts + clock_skew:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="clock_skew",
            )
        if now_ts - auth_date > max_age:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="init_data_expired",
            )
        return parsed

    if bad_hash_format:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="bad_hash_format",
        )
    if not has_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="init_data_invalid",
        )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="init_data_invalid",
    )


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
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="bot_token_missing")
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
