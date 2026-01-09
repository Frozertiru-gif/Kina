from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db_session
from app.models import Title, TitleType, ViewEvent

router = APIRouter()


def _parse_period(period: str) -> timedelta:
    if not period:
        return timedelta(days=30)
    if period.endswith("d") and period[:-1].isdigit():
        return timedelta(days=int(period[:-1]))
    return timedelta(days=30)


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


@router.get("/catalog/top")
async def catalog_top(
    period: str = Query("30d"),
    type: TitleType | None = Query(default=None),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    delta = _parse_period(period)
    since = datetime.now(timezone.utc) - delta

    query = (
        select(ViewEvent.title_id, func.count(ViewEvent.id).label("views"))
        .join(Title, Title.id == ViewEvent.title_id)
        .where(ViewEvent.created_at >= since, Title.is_published.is_(True))
        .group_by(ViewEvent.title_id)
        .order_by(func.count(ViewEvent.id).desc())
        .limit(limit)
    )
    if type:
        query = query.where(Title.type == type)

    result = await session.execute(query)
    top_ids = [row.title_id for row in result.all()]

    if not top_ids:
        fallback_query = (
            select(Title)
            .where(Title.is_published.is_(True))
            .order_by(Title.created_at.desc())
            .limit(limit)
        )
        if type:
            fallback_query = fallback_query.where(Title.type == type)
        fallback = await session.execute(fallback_query)
        return [_title_to_dict(title) for title in fallback.scalars().all()]

    ordering = case({title_id: index for index, title_id in enumerate(top_ids)}, value=Title.id)
    titles_result = await session.execute(
        select(Title).where(Title.id.in_(top_ids)).order_by(ordering)
    )
    return [_title_to_dict(title) for title in titles_result.scalars().all()]


@router.get("/catalog/search")
async def catalog_search(
    q: str = Query(""),
    type: TitleType | None = Query(default=None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    query = select(Title).where(Title.is_published.is_(True))
    if q:
        pattern = f"%{q}%"
        query = query.where(or_(Title.name.ilike(pattern), Title.original_name.ilike(pattern)))
    if type:
        query = query.where(Title.type == type)
    query = query.order_by(Title.created_at.desc()).limit(limit).offset(offset)

    result = await session.execute(query)
    return [_title_to_dict(title) for title in result.scalars().all()]
