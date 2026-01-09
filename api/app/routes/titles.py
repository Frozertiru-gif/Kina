from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db_session
from app.models import Episode, MediaVariant, Season, Title, TitleType

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


@router.get("/title/{title_id}")
async def get_title(
    title_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await session.execute(select(Title).where(Title.id == title_id))
    title = result.scalar_one_or_none()
    if not title:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="title_not_found")

    response = _title_to_dict(title)

    if title.type == TitleType.SERIES:
        counts_subquery = (
            select(Episode.season_id, func.count(Episode.id).label("episodes_count"))
            .where(Episode.title_id == title_id)
            .group_by(Episode.season_id)
            .subquery()
        )
        seasons_result = await session.execute(
            select(
                Season,
                func.coalesce(counts_subquery.c.episodes_count, 0).label("episodes_count"),
            )
            .outerjoin(counts_subquery, counts_subquery.c.season_id == Season.id)
            .where(Season.title_id == title_id)
            .order_by(Season.season_number)
        )
        seasons = []
        total_episodes = 0
        for season, episodes_count in seasons_result.all():
            total_episodes += episodes_count
            seasons.append(
                {
                    "id": season.id,
                    "season_number": season.season_number,
                    "name": season.name,
                    "episodes_count": episodes_count,
                }
            )
        response["seasons"] = seasons
        response["episodes_count"] = total_episodes
    else:
        response["seasons"] = []
        response["episodes_count"] = 0

    variants_query = select(MediaVariant).where(MediaVariant.title_id == title_id)
    if title.type == TitleType.MOVIE:
        variants_query = variants_query.where(MediaVariant.episode_id.is_(None))
    variants_result = await session.execute(variants_query)
    variants = variants_result.scalars().all()

    response["available_audio_ids"] = sorted({variant.audio_id for variant in variants})
    response["available_quality_ids"] = sorted({variant.quality_id for variant in variants})

    return response


@router.get("/title/{title_id}/episodes")
async def list_episodes(
    title_id: int,
    season: int = Query(1, ge=1),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    season_result = await session.execute(
        select(Season).where(Season.title_id == title_id, Season.season_number == season)
    )
    season_obj = season_result.scalar_one_or_none()
    if not season_obj:
        return []

    episodes_result = await session.execute(
        select(Episode)
        .where(Episode.season_id == season_obj.id)
        .order_by(Episode.episode_number)
    )
    return [
        {
            "id": episode.id,
            "episode_number": episode.episode_number,
            "name": episode.name,
            "published_at": episode.published_at,
        }
        for episode in episodes_result.scalars().all()
    ]
