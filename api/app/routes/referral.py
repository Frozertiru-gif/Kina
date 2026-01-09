import os

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import CurrentUser, get_current_user, get_db_session
from app.services.referrals import ensure_referral_code

router = APIRouter()


class ReferralMeResponse(BaseModel):
    code: str
    link: str


@router.get("/referral/me", response_model=ReferralMeResponse)
async def get_referral_me(
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ReferralMeResponse:
    code = await ensure_referral_code(session, user.id)
    base_url = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    link = f"{base_url}?startapp=ref_{code}" if base_url else f"?startapp=ref_{code}"
    return ReferralMeResponse(code=code, link=link)
