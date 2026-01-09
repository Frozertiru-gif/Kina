import os
import secrets
import string

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Referral, ReferralCode, ReferralReward, User
from app.services.premium import apply_premium_days


def get_referral_reward_days() -> int:
    raw = os.getenv("REFERRAL_REWARD_DAYS", "7")
    try:
        return int(raw)
    except ValueError:
        return 7


def _generate_code(length: int = 10) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def ensure_referral_code(session: AsyncSession, user_id: int) -> str:
    result = await session.execute(select(ReferralCode).where(ReferralCode.user_id == user_id))
    existing = result.scalar_one_or_none()
    if existing:
        return existing.code

    for _ in range(10):
        code = _generate_code()
        collision = await session.execute(select(ReferralCode).where(ReferralCode.code == code))
        if collision.scalar_one_or_none():
            continue
        referral_code = ReferralCode(user_id=user_id, code=code)
        session.add(referral_code)
        await session.commit()
        return referral_code.code

    raise RuntimeError("Failed to generate unique referral code")


async def apply_referral_code(
    session: AsyncSession,
    referred_user: User,
    code: str,
    reward_days: int,
    reason: str = "referral_signup",
) -> bool:
    trimmed = code.strip()
    if not trimmed:
        return False

    ref_code_result = await session.execute(
        select(ReferralCode).where(ReferralCode.code == trimmed)
    )
    ref_code = ref_code_result.scalar_one_or_none()
    if not ref_code:
        return False
    if ref_code.user_id == referred_user.id:
        return False

    existing = await session.execute(
        select(Referral).where(Referral.referred_user_id == referred_user.id)
    )
    if existing.scalar_one_or_none():
        return False

    referral = Referral(referrer_user_id=ref_code.user_id, referred_user_id=referred_user.id)
    reward = ReferralReward(
        referrer_user_id=ref_code.user_id,
        referred_user_id=referred_user.id,
        reward_days=reward_days,
        reason=reason,
    )
    session.add_all([referral, reward])
    await session.flush()
    await apply_premium_days(session, ref_code.user_id, reward_days, reason, reward)
    return True
