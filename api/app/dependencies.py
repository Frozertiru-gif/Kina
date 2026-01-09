import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl

from fastapi import Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models import User, UserPremium


class CurrentUser(BaseModel):
    id: int
    tg_user_id: int
    username: str | None
    first_name: str | None
    premium_until: datetime | None


async def get_db_session() -> AsyncSession:
    async with SessionLocal() as session:
        yield session


def _is_dev_bypass_allowed() -> bool:
    environment = os.getenv("ENVIRONMENT")
    dev_bypass = os.getenv("DEV_AUTH_BYPASS", "false").lower() == "true"
    return environment == "local" and dev_bypass


def _get_dev_user_id(x_dev_user_id: str | None) -> int:
    if x_dev_user_id:
        return int(x_dev_user_id)
    env_user_id = os.getenv("DEV_TG_USER_ID")
    if env_user_id:
        return int(env_user_id)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="dev_user_id_required",
    )


def _parse_init_data(init_data: str) -> dict[str, Any]:
    return dict(parse_qsl(init_data, strict_parsing=False, keep_blank_values=True))


def _validate_init_data(init_data: str, bot_token: str) -> dict[str, Any]:
    parsed = _parse_init_data(init_data)
    provided_hash = parsed.pop("hash", None)
    if not provided_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="init_data_missing_hash",
        )
    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(parsed.items())
    )
    secret = hashlib.sha256(bot_token.encode("utf-8")).digest()
    calculated_hash = hmac.new(
        secret, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(calculated_hash, provided_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="init_data_invalid",
        )
    return parsed


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


async def get_current_user(
    x_init_data: str | None = Header(default=None, alias="X-Init-Data"),
    x_dev_user_id: str | None = Header(default=None, alias="X-Dev-User-Id"),
    session: AsyncSession = Depends(get_db_session),
) -> CurrentUser:
    if _is_dev_bypass_allowed():
        tg_user_id = _get_dev_user_id(x_dev_user_id)
        user = await _upsert_user(session, tg_user_id, None, None, None)
        premium_until = await _get_premium_until(session, user.id)
        return CurrentUser(
            id=user.id,
            tg_user_id=user.tg_user_id,
            username=user.username,
            first_name=user.first_name,
            premium_until=premium_until,
        )

    if not x_init_data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="init_data_required")
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


def get_service_token(
    x_service_token: str | None = Header(default=None, alias="X-Service-Token"),
) -> None:
    expected = os.getenv("SERVICE_TOKEN")
    if not expected or x_service_token != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_service_token")
