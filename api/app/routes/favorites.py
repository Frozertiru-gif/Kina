from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import CurrentUser, get_current_user, get_db_session
from app.models import Favorite, Title

router = APIRouter()


def _title_to_dict(title: Title) -> dict:
    return {
        "id": title.id,
        "type": title.type.value,
        "name": title.name,
        "original_name": title.original_name,
        "description": title.description,
        "year": title.year,
        "poster_url": title.poster_url,
        "is_published": title.is_published,
    }


class FavoriteToggleRequest(BaseModel):
    title_id: int


@router.get("/favorites")
async def list_favorites(
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    result = await session.execute(
        select(Title)
        .join(Favorite, Favorite.title_id == Title.id)
        .where(Favorite.user_id == user.id)
        .order_by(Favorite.created_at.desc())
    )
    return [_title_to_dict(title) for title in result.scalars().all()]


@router.post("/favorites/toggle")
async def toggle_favorite(
    payload: FavoriteToggleRequest,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await session.execute(
        select(Favorite).where(
            Favorite.user_id == user.id,
            Favorite.title_id == payload.title_id,
        )
    )
    favorite = result.scalar_one_or_none()
    if favorite:
        await session.delete(favorite)
        await session.commit()
        return {"title_id": payload.title_id, "favorited": False}

    title_result = await session.execute(select(Title).where(Title.id == payload.title_id))
    title = title_result.scalar_one_or_none()
    if not title:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="title_not_found")

    session.add(Favorite(user_id=user.id, title_id=payload.title_id))
    await session.commit()
    return {"title_id": payload.title_id, "favorited": True}
