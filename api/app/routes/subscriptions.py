from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import CurrentUser, get_current_user, get_db_session
from app.models import Subscription, Title, TitleType
from app.services.audit import log_audit_event

router = APIRouter()


class SubscriptionToggleRequest(BaseModel):
    title_id: int


@router.get("/subscriptions")
async def list_subscriptions(
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    result = await session.execute(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    return [
        {"title_id": subscription.title_id, "enabled": subscription.enabled}
        for subscription in result.scalars().all()
    ]


@router.post("/subscriptions/toggle")
async def toggle_subscription(
    payload: SubscriptionToggleRequest,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    title_result = await session.execute(select(Title).where(Title.id == payload.title_id))
    title = title_result.scalar_one_or_none()
    if not title:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="title_not_found")
    if title.type != TitleType.SERIES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="series_only")

    result = await session.execute(
        select(Subscription).where(
            Subscription.user_id == user.id,
            Subscription.title_id == payload.title_id,
        )
    )
    subscription = result.scalar_one_or_none()
    if subscription:
        subscription.enabled = not subscription.enabled
        await log_audit_event(
            session,
            actor_type="user",
            actor_user_id=user.id,
            actor_admin_id=None,
            action="subscription_toggled",
            entity_type="subscription",
            entity_id=payload.title_id,
            metadata_json={"enabled": subscription.enabled},
        )
        await session.commit()
        return {"title_id": payload.title_id, "enabled": subscription.enabled}

    session.add(Subscription(user_id=user.id, title_id=payload.title_id, enabled=True))
    await log_audit_event(
        session,
        actor_type="user",
        actor_user_id=user.id,
        actor_admin_id=None,
        action="subscription_toggled",
        entity_type="subscription",
        entity_id=payload.title_id,
        metadata_json={"enabled": True},
    )
    await session.commit()
    return {"title_id": payload.title_id, "enabled": True}
