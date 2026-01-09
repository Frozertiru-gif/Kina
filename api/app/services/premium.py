from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ReferralReward, UserPremium
from app.services.audit import log_audit_event


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
        await log_audit_event(
            session,
            actor_type="service",
            actor_user_id=None,
            actor_admin_id=None,
            action="referral_reward_applied",
            entity_type="referral_reward",
            entity_id=reward.id,
            metadata_json={
                "referrer_user_id": reward.referrer_user_id,
                "referred_user_id": reward.referred_user_id,
                "reward_days": reward.reward_days,
            },
        )

    await session.commit()
    await session.refresh(premium)
    return premium.premium_until
