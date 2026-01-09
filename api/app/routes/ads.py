import json
import os
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.dependencies import CurrentUser, get_current_user
from app.redis import get_redis, json_set, setnx_with_ttl

router = APIRouter()


class AdsStartRequest(BaseModel):
    variant_id: int


class AdsCompleteRequest(BaseModel):
    nonce: str


def _get_ads_env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


@router.post("/ads/start")
async def ads_start(
    payload: AdsStartRequest,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    cooldown_ttl = _get_ads_env_int("ADS_COOLDOWN_SECONDS", 90)
    nonce_ttl = _get_ads_env_int("ADS_NONCE_TTL_SECONDS", 300)
    cooldown_key = f"ad_cd:{user.tg_user_id}"
    allowed = await setnx_with_ttl(cooldown_key, cooldown_ttl)
    if not allowed:
        redis = get_redis()
        retry_after = await redis.ttl(cooldown_key)
        retry_after = retry_after if retry_after and retry_after > 0 else cooldown_ttl
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"error": "ad_cooldown", "retry_after": retry_after},
        )

    nonce = secrets.token_urlsafe(32)
    nonce_payload = {
        "tg_user_id": user.tg_user_id,
        "variant_id": payload.variant_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await json_set(f"ad_nonce:{nonce}", nonce_ttl, nonce_payload)

    return {"nonce": nonce, "ttl": nonce_ttl}


@router.post("/ads/complete")
async def ads_complete(
    payload: AdsCompleteRequest,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    redis = get_redis()
    nonce_key = f"ad_nonce:{payload.nonce}"
    raw_payload = await redis.get(nonce_key)
    if not raw_payload:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "invalid_or_expired_nonce"},
        )

    nonce_payload = json.loads(raw_payload)
    if nonce_payload.get("tg_user_id") != user.tg_user_id:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"error": "nonce_user_mismatch"},
        )

    await redis.delete(nonce_key)
    pass_ttl = _get_ads_env_int("ADS_PASS_TTL_SECONDS", 900)
    variant_id = int(nonce_payload["variant_id"])
    pass_key = f"ad_pass:{user.tg_user_id}:{variant_id}"
    await redis.set(pass_key, "1", ex=pass_ttl)

    return {"ok": True, "pass_ttl": pass_ttl, "variant_id": variant_id}


@router.get("/ads/status")
async def ads_status(
    variant_id: int,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    redis = get_redis()
    pass_key = f"ad_pass:{user.tg_user_id}:{variant_id}"
    exists = bool(await redis.exists(pass_key))
    pass_ttl = None
    if exists:
        ttl = await redis.ttl(pass_key)
        if ttl is not None and ttl >= 0:
            pass_ttl = ttl

    return {"has_pass": exists, "pass_ttl": pass_ttl}
