import os

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import CurrentUser, get_current_user, get_db_session
from app.services.rate_limit import rate_limit_response, register_violation
from app.models import User
from app.services.referrals import (
    ReferralRateLimitError,
    apply_referral_code,
    ensure_referral_code,
    get_referral_reward_days,
)

router = APIRouter()


class ReferralMeResponse(BaseModel):
    code: str
    link: str


class ReferralApplyRequest(BaseModel):
    code: str


@router.get("/referral/me", response_model=ReferralMeResponse)
async def get_referral_me(
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ReferralMeResponse:
    code = await ensure_referral_code(session, user.id)
    base_url = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    link = f"{base_url}?startapp=ref_{code}" if base_url else f"?startapp=ref_{code}"
    return ReferralMeResponse(code=code, link=link)


@router.post("/referral/apply")
async def apply_referral(
    payload: ReferralApplyRequest,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    db_user = await session.get(User, user.id)
    if db_user is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": "user_not_found"},
        )
    try:
        applied = await apply_referral_code(
            session,
            db_user,
            payload.code,
            get_referral_reward_days(),
            actor_type="user",
        )
    except ReferralRateLimitError as exc:
        await register_violation(session, user.tg_user_id)
        return rate_limit_response(exc.retry_after)
    return {"applied": applied}
