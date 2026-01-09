from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ReferralReward, UserPremium


async def apply_premium_days(
    session: AsyncSession,
    user_id: int,
    days: int,
    reason: str,
    reward: ReferralReward | None = None,
) -> datetime:
    now = datetime.now(timezone.utc)
    result = await session.execute(select(UserPremium).where(UserPremium.user_id == user_id))
    premium = result.scalar_one_or_none()
    if premium is None:
        premium = UserPremium(user_id=user_id, premium_until=now + timedelta(days=days))
        session.add(premium)
    else:
        if premium.premium_until < now:
            premium.premium_until = now + timedelta(days=days)
        else:
            premium.premium_until = premium.premium_until + timedelta(days=days)

    if reward:
        reward.applied = True
        reward.applied_at = now

    await session.commit()
    await session.refresh(premium)
    return premium.premium_until
