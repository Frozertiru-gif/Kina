import json
import logging
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_admin_token, get_db_session
from app.models import (
    AudioTrack,
    Episode,
    MediaVariant,
    Quality,
    Referral,
    ReferralReward,
    Season,
    Title,
    TitleType,
    UploadJob,
    Subscription,
    User,
    UserPremium,
)
from app.redis import get_redis
from app.services.audit import log_audit_event
from app.services.premium import apply_premium_days

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger("kina.api.admin")


async def _log_admin_event(
    session: AsyncSession,
    admin_info: dict,
    *,
    action: str,
    entity_type: str,
    entity_id: int | None,
    metadata: dict | None = None,
) -> None:
    payload = {"admin_tg_user_id": admin_info.get("tg_user_id")}
    if metadata:
        payload.update(metadata)
    await log_audit_event(
        session,
        actor_type="admin",
        actor_user_id=None,
        actor_admin_id=None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata_json=payload,
    )


async def _enqueue_publish_notifications(
    session: AsyncSession,
    admin_info: dict,
    episode: Episode,
) -> None:
    if not episode.published_at:
        return
    episode_result = await session.execute(
        select(Season, Title)
        .join(Title, Season.title_id == Title.id)
        .where(Season.id == episode.season_id)
    )
    row = episode_result.first()
    if not row:
        return
    season, title = row
    if title.type != TitleType.SERIES:
        return
    variant_result = await session.execute(
        select(MediaVariant)
        .where(
            MediaVariant.episode_id == episode.id,
            MediaVariant.status == "ready",
        )
        .order_by(MediaVariant.updated_at.desc())
        .limit(1)
    )
    variant = variant_result.scalar_one_or_none()
    if not variant:
        return
    result = await session.execute(
        select(User.tg_user_id)
        .join(Subscription, Subscription.user_id == User.id)
        .where(
            Subscription.title_id == title.id,
            Subscription.enabled.is_(True),
        )
    )
    tg_user_ids = [row[0] for row in result.fetchall()]
    if not tg_user_ids:
        return

    redis = get_redis()
    text = (
        "Новая серия вышла: "
        f"{title.name} — S{season.season_number}E{episode.episode_number}. Открыть?"
    )
    enqueued = 0
    deduped = 0
    for tg_user_id in tg_user_ids:
        dedupe_key = f"notif:{tg_user_id}:{episode.id}"
        dedupe_set = await redis.set(dedupe_key, "1", nx=True, ex=60 * 60 * 24 * 7)
        if not dedupe_set:
            deduped += 1
            continue
        payload = {
            "tg_user_id": tg_user_id,
            "title_id": title.id,
            "episode_id": episode.id,
            "text": text,
            "variant_id": variant.id,
        }
        await redis.rpush("notify_queue", json.dumps(payload, ensure_ascii=False))
        enqueued += 1

    await _log_admin_event(
        session,
        admin_info,
        action="notification_enqueued",
        entity_type="episode",
        entity_id=episode.id,
        metadata={
            "title_id": title.id,
            "variant_id": variant.id,
            "total_subscribers": len(tg_user_ids),
            "enqueued": enqueued,
            "deduped": deduped,
        },
    )
    await session.commit()


class TitleCreate(BaseModel):
    type: TitleType
    name: str
    original_name: str | None = None
    description: str | None = None
    year: int | None = None
    poster_url: str | None = None
    is_published: bool | None = None


class TitleUpdate(BaseModel):
    type: TitleType | None = None
    name: str | None = None
    original_name: str | None = None
    description: str | None = None
    year: int | None = None
    poster_url: str | None = None
    is_published: bool | None = None


class SeasonCreate(BaseModel):
    season_number: int
    name: str | None = None


class EpisodeCreate(BaseModel):
    episode_number: int
    name: str
    description: str | None = None
    air_date: date | None = None


class EpisodeUpdate(BaseModel):
    episode_number: int | None = None
    name: str | None = None
    description: str | None = None
    air_date: date | None = None


class AudioTrackCreate(BaseModel):
    name: str
    code: str
    is_active: bool = True


class AudioTrackUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    is_active: bool | None = None


class QualityCreate(BaseModel):
    name: str
    height: int
    is_active: bool = True


class QualityUpdate(BaseModel):
    name: str | None = None
    height: int | None = None
    is_active: bool | None = None


class VariantCreate(BaseModel):
    title_id: int
    episode_id: int | None = None
    audio_id: int
    quality_id: int
    status: str = "pending"
    error: str | None = None
    telegram_file_id: str | None = None
    storage_chat_id: int | None = None
    storage_message_id: int | None = None
    duration_sec: int | None = None
    size_bytes: int | None = None
    checksum_sha256: str | None = None


class VariantUpdate(BaseModel):
    title_id: int | None = None
    episode_id: int | None = None
    audio_id: int | None = None
    quality_id: int | None = None
    status: str | None = None
    error: str | None = None
    telegram_file_id: str | None = None
    storage_chat_id: int | None = None
    storage_message_id: int | None = None
    duration_sec: int | None = None
    size_bytes: int | None = None
    checksum_sha256: str | None = None


class PremiumGrantRequest(BaseModel):
    days: int = Field(..., ge=1)
    reason: str


class PremiumRevokeRequest(BaseModel):
    reason: str


class UserBanRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=255)


def _expected_filename(title_id: int, episode_id: int | None, audio_id: int, quality_id: int) -> str:
    if episode_id is None:
        return f"title_{title_id}__a_{audio_id}__q_{quality_id}.mp4"
    return f"ep_{episode_id}__a_{audio_id}__q_{quality_id}.mp4"


def _serialize_variant(variant: MediaVariant) -> dict:
    return {
        "id": variant.id,
        "title_id": variant.title_id,
        "episode_id": variant.episode_id,
        "audio_id": variant.audio_id,
        "quality_id": variant.quality_id,
        "telegram_file_id": variant.telegram_file_id,
        "storage_chat_id": variant.storage_chat_id,
        "storage_message_id": variant.storage_message_id,
        "status": variant.status,
        "error": variant.error,
        "duration_sec": variant.duration_sec,
        "size_bytes": variant.size_bytes,
        "checksum_sha256": variant.checksum_sha256,
        "created_at": variant.created_at,
        "updated_at": variant.updated_at,
        "expected_filename": _expected_filename(
            variant.title_id, variant.episode_id, variant.audio_id, variant.quality_id
        ),
    }


@router.get("/titles")
async def list_titles(
    type: TitleType | None = Query(default=None),
    q: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: dict = Depends(get_admin_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    query = select(Title)
    if type:
        query = query.where(Title.type == type)
    if q:
        query = query.where(Title.name.ilike(f"%{q}%"))
    total_result = await session.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar_one()
    result = await session.execute(query.order_by(Title.id.desc()).limit(limit).offset(offset))
    titles = result.scalars().all()
    return {
        "items": [
            {
                "id": title.id,
                "type": title.type.value,
                "name": title.name,
                "original_name": title.original_name,
                "description": title.description,
                "year": title.year,
                "poster_url": title.poster_url,
                "is_published": title.is_published,
                "created_at": title.created_at,
                "updated_at": title.updated_at,
            }
            for title in titles
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/titles", status_code=status.HTTP_201_CREATED)
async def create_title(
    payload: TitleCreate,
    admin_info: dict = Depends(get_admin_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    title = Title(
        type=payload.type,
        name=payload.name,
        original_name=payload.original_name,
        description=payload.description,
        year=payload.year,
        poster_url=payload.poster_url,
    )
    if payload.is_published is not None:
        title.is_published = payload.is_published
    session.add(title)
    await session.flush()
    await _log_admin_event(
        session,
        admin_info,
        action="title_created",
        entity_type="title",
        entity_id=title.id,
        metadata={"name": title.name},
    )
    await session.commit()
    await session.refresh(title)
    return {"id": title.id}


@router.get("/titles/{title_id}")
async def get_title(
    title_id: int,
    _: dict = Depends(get_admin_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    title = await session.get(Title, title_id)
    if not title:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="title_not_found")
    seasons_result = await session.execute(
        select(Season).where(Season.title_id == title_id).order_by(Season.season_number)
    )
    seasons = seasons_result.scalars().all()
    episodes_result = await session.execute(
        select(Episode)
        .where(Episode.title_id == title_id)
        .order_by(Episode.season_id, Episode.episode_number)
    )
    episodes = episodes_result.scalars().all()
    episodes_by_season: dict[int, list[Episode]] = {}
    for episode in episodes:
        episodes_by_season.setdefault(episode.season_id, []).append(episode)
    return {
        "id": title.id,
        "type": title.type.value,
        "name": title.name,
        "original_name": title.original_name,
        "description": title.description,
        "year": title.year,
        "poster_url": title.poster_url,
        "is_published": title.is_published,
        "created_at": title.created_at,
        "updated_at": title.updated_at,
        "seasons": [
            {
                "id": season.id,
                "season_number": season.season_number,
                "name": season.name,
                "created_at": season.created_at,
                "episodes": [
                    {
                        "id": episode.id,
                        "episode_number": episode.episode_number,
                        "name": episode.name,
                        "description": episode.description,
                        "air_date": episode.air_date,
                        "published_at": episode.published_at,
                        "created_at": episode.created_at,
                    }
                    for episode in episodes_by_season.get(season.id, [])
                ],
            }
            for season in seasons
        ],
    }


@router.patch("/titles/{title_id}")
async def update_title(
    title_id: int,
    payload: TitleUpdate,
    admin_info: dict = Depends(get_admin_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    title = await session.get(Title, title_id)
    if not title:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="title_not_found")
    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(title, key, value)
    await _log_admin_event(
        session,
        admin_info,
        action="title_updated",
        entity_type="title",
        entity_id=title.id,
        metadata={"fields": list(update_data.keys())},
    )
    await session.commit()
    await session.refresh(title)
    return {"id": title.id}


@router.post("/titles/{title_id}/seasons", status_code=status.HTTP_201_CREATED)
async def create_season(
    title_id: int,
    payload: SeasonCreate,
    admin_info: dict = Depends(get_admin_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    title = await session.get(Title, title_id)
    if not title:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="title_not_found")
    season = Season(title_id=title_id, season_number=payload.season_number, name=payload.name)
    session.add(season)
    await session.flush()
    await _log_admin_event(
        session,
        admin_info,
        action="season_created",
        entity_type="season",
        entity_id=season.id,
        metadata={"title_id": title_id, "season_number": payload.season_number},
    )
    await session.commit()
    await session.refresh(season)
    return {"id": season.id}


@router.post("/seasons/{season_id}/episodes", status_code=status.HTTP_201_CREATED)
async def create_episode(
    season_id: int,
    payload: EpisodeCreate,
    admin_info: dict = Depends(get_admin_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    season = await session.get(Season, season_id)
    if not season:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="season_not_found")
    episode = Episode(
        title_id=season.title_id,
        season_id=season_id,
        episode_number=payload.episode_number,
        name=payload.name,
        description=payload.description,
        air_date=payload.air_date,
    )
    session.add(episode)
    await session.flush()
    await _log_admin_event(
        session,
        admin_info,
        action="episode_created",
        entity_type="episode",
        entity_id=episode.id,
        metadata={"title_id": season.title_id, "season_id": season_id},
    )
    await session.commit()
    await session.refresh(episode)
    return {"id": episode.id}


@router.patch("/episodes/{episode_id}")
async def update_episode(
    episode_id: int,
    payload: EpisodeUpdate,
    admin_info: dict = Depends(get_admin_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    episode = await session.get(Episode, episode_id)
    if not episode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="episode_not_found")
    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(episode, key, value)
    await _log_admin_event(
        session,
        admin_info,
        action="episode_updated",
        entity_type="episode",
        entity_id=episode.id,
        metadata={"fields": list(update_data.keys())},
    )
    await session.commit()
    await session.refresh(episode)
    return {"id": episode.id}


@router.post("/episodes/{episode_id}/publish")
async def publish_episode(
    episode_id: int,
    admin_info: dict = Depends(get_admin_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    episode = await session.get(Episode, episode_id)
    if not episode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="episode_not_found")
    episode.published_at = datetime.now(timezone.utc)
    await _log_admin_event(
        session,
        admin_info,
        action="episode_published",
        entity_type="episode",
        entity_id=episode.id,
        metadata={"published_at": episode.published_at.isoformat()},
    )
    await session.commit()
    await session.refresh(episode)
    await _enqueue_publish_notifications(session, admin_info, episode)
    return {"id": episode.id, "published_at": episode.published_at}


@router.get("/audio_tracks")
async def list_audio_tracks(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: dict = Depends(get_admin_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    total_result = await session.execute(select(func.count()).select_from(AudioTrack))
    total = total_result.scalar_one()
    result = await session.execute(
        select(AudioTrack).order_by(AudioTrack.id.desc()).limit(limit).offset(offset)
    )
    tracks = result.scalars().all()
    return {
        "items": [
            {
                "id": track.id,
                "name": track.name,
                "code": track.code,
                "is_active": track.is_active,
            }
            for track in tracks
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/audio_tracks", status_code=status.HTTP_201_CREATED)
async def create_audio_track(
    payload: AudioTrackCreate,
    admin_info: dict = Depends(get_admin_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    track = AudioTrack(name=payload.name, code=payload.code, is_active=payload.is_active)
    session.add(track)
    await session.flush()
    await _log_admin_event(
        session,
        admin_info,
        action="audio_track_created",
        entity_type="audio_track",
        entity_id=track.id,
        metadata={"code": track.code},
    )
    await session.commit()
    await session.refresh(track)
    return {"id": track.id}


@router.patch("/audio_tracks/{track_id}")
async def update_audio_track(
    track_id: int,
    payload: AudioTrackUpdate,
    admin_info: dict = Depends(get_admin_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    track = await session.get(AudioTrack, track_id)
    if not track:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="audio_track_not_found")
    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(track, key, value)
    await _log_admin_event(
        session,
        admin_info,
        action="audio_track_updated",
        entity_type="audio_track",
        entity_id=track.id,
        metadata={"fields": list(update_data.keys())},
    )
    await session.commit()
    await session.refresh(track)
    return {"id": track.id}


@router.get("/qualities")
async def list_qualities(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: dict = Depends(get_admin_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    total_result = await session.execute(select(func.count()).select_from(Quality))
    total = total_result.scalar_one()
    result = await session.execute(
        select(Quality).order_by(Quality.id.desc()).limit(limit).offset(offset)
    )
    qualities = result.scalars().all()
    return {
        "items": [
            {
                "id": quality.id,
                "name": quality.name,
                "height": quality.height,
                "is_active": quality.is_active,
            }
            for quality in qualities
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/qualities", status_code=status.HTTP_201_CREATED)
async def create_quality(
    payload: QualityCreate,
    admin_info: dict = Depends(get_admin_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    quality = Quality(name=payload.name, height=payload.height, is_active=payload.is_active)
    session.add(quality)
    await session.flush()
    await _log_admin_event(
        session,
        admin_info,
        action="quality_created",
        entity_type="quality",
        entity_id=quality.id,
        metadata={"height": quality.height},
    )
    await session.commit()
    await session.refresh(quality)
    return {"id": quality.id}


@router.patch("/qualities/{quality_id}")
async def update_quality(
    quality_id: int,
    payload: QualityUpdate,
    admin_info: dict = Depends(get_admin_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    quality = await session.get(Quality, quality_id)
    if not quality:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="quality_not_found")
    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(quality, key, value)
    await _log_admin_event(
        session,
        admin_info,
        action="quality_updated",
        entity_type="quality",
        entity_id=quality.id,
        metadata={"fields": list(update_data.keys())},
    )
    await session.commit()
    await session.refresh(quality)
    return {"id": quality.id}


@router.post("/variants", status_code=status.HTTP_201_CREATED)
async def create_variant(
    payload: VariantCreate,
    admin_info: dict = Depends(get_admin_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    title = await session.get(Title, payload.title_id)
    if not title:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="title_not_found")
    if payload.episode_id is not None:
        episode = await session.get(Episode, payload.episode_id)
        if not episode:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="episode_not_found")
        if episode.title_id != payload.title_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="episode_title_mismatch")
    variant = MediaVariant(
        title_id=payload.title_id,
        episode_id=payload.episode_id,
        audio_id=payload.audio_id,
        quality_id=payload.quality_id,
        status=payload.status,
        error=payload.error,
        telegram_file_id=payload.telegram_file_id,
        storage_chat_id=payload.storage_chat_id,
        storage_message_id=payload.storage_message_id,
        duration_sec=payload.duration_sec,
        size_bytes=payload.size_bytes,
        checksum_sha256=payload.checksum_sha256,
    )
    session.add(variant)
    await session.flush()
    await _log_admin_event(
        session,
        admin_info,
        action="variant_created",
        entity_type="media_variant",
        entity_id=variant.id,
        metadata={
            "title_id": variant.title_id,
            "episode_id": variant.episode_id,
            "status": variant.status,
        },
    )
    await session.commit()
    await session.refresh(variant)
    return _serialize_variant(variant)


@router.patch("/variants/{variant_id}")
async def update_variant(
    variant_id: int,
    payload: VariantUpdate,
    admin_info: dict = Depends(get_admin_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    variant = await session.get(MediaVariant, variant_id)
    if not variant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="variant_not_found")
    update_data = payload.model_dump(exclude_unset=True)
    if "title_id" in update_data:
        title = await session.get(Title, update_data["title_id"])
        if not title:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="title_not_found")
    if "episode_id" in update_data and update_data["episode_id"] is not None:
        episode = await session.get(Episode, update_data["episode_id"])
        if not episode:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="episode_not_found")
        if "title_id" in update_data and episode.title_id != update_data["title_id"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="episode_title_mismatch")
    for key, value in update_data.items():
        setattr(variant, key, value)
    await _log_admin_event(
        session,
        admin_info,
        action="variant_updated",
        entity_type="media_variant",
        entity_id=variant.id,
        metadata={"fields": list(update_data.keys())},
    )
    await session.commit()
    await session.refresh(variant)
    return _serialize_variant(variant)


@router.get("/variants")
async def list_variants(
    title_id: int | None = Query(default=None),
    episode_id: int | None = Query(default=None),
    status: str | None = Query(default=None, max_length=50),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: dict = Depends(get_admin_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    query = select(MediaVariant)
    if title_id:
        query = query.where(MediaVariant.title_id == title_id)
    if episode_id:
        query = query.where(MediaVariant.episode_id == episode_id)
    if status:
        query = query.where(MediaVariant.status == status)
    total_result = await session.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar_one()
    result = await session.execute(
        query.order_by(MediaVariant.id.desc()).limit(limit).offset(offset)
    )
    variants = result.scalars().all()
    return {
        "items": [_serialize_variant(variant) for variant in variants],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/upload_jobs")
async def list_upload_jobs(
    status: str | None = Query(default=None, max_length=50),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: dict = Depends(get_admin_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    query = select(UploadJob)
    if status:
        query = query.where(UploadJob.status == status)
    total_result = await session.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar_one()
    result = await session.execute(
        query.order_by(UploadJob.id.desc()).limit(limit).offset(offset)
    )
    jobs = result.scalars().all()
    return {
        "items": [
            {
                "id": job.id,
                "variant_id": job.variant_id,
                "status": job.status,
                "attempts": job.attempts,
                "local_path": job.local_path,
                "last_error": job.last_error,
                "created_at": job.created_at,
                "updated_at": job.updated_at,
            }
            for job in jobs
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/upload_jobs/{job_id}/retry")
async def retry_upload_job(
    job_id: int,
    admin_info: dict = Depends(get_admin_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    job = await session.get(UploadJob, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job_not_found")
    job.status = "queued"
    job.last_error = None
    job.attempts = 0
    variant = await session.get(MediaVariant, job.variant_id)
    if variant:
        variant.status = "uploading"
        variant.error = None
    await _log_admin_event(
        session,
        admin_info,
        action="upload_job_retry",
        entity_type="upload_job",
        entity_id=job.id,
        metadata={"variant_id": job.variant_id},
    )
    await session.commit()
    return {"job_id": job.id, "status": job.status}


@router.post("/upload_jobs/rescan")
async def rescan_upload_jobs(
    admin_info: dict = Depends(get_admin_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    redis = get_redis()
    await redis.rpush("uploader_control_queue", json.dumps({"action": "rescan"}))
    await _log_admin_event(
        session,
        admin_info,
        action="upload_jobs_rescan",
        entity_type="upload_job",
        entity_id=None,
    )
    await session.commit()
    return {"queued": True}


@router.get("/users")
async def list_users(
    q: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: dict = Depends(get_admin_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    query = select(User, UserPremium.premium_until).outerjoin(
        UserPremium, UserPremium.user_id == User.id
    )
    if q:
        filters = [User.username.ilike(f"%{q}%")]
        if q.isdigit():
            filters.append(User.tg_user_id == int(q))
        query = query.where(or_(*filters))
    total_result = await session.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar_one()
    result = await session.execute(query.order_by(User.id.desc()).limit(limit).offset(offset))
    rows = result.all()
    return {
        "items": [
            {
                "id": user.id,
                "tg_user_id": user.tg_user_id,
                "username": user.username,
                "first_name": user.first_name,
                "premium_until": premium_until,
                "is_banned": user.is_banned,
                "ban_reason": user.ban_reason,
                "created_at": user.created_at,
            }
            for user, premium_until in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/users/{user_id}/ban")
async def ban_user(
    user_id: int,
    payload: UserBanRequest,
    admin_info: dict = Depends(get_admin_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")
    user.is_banned = True
    user.ban_reason = payload.reason
    await _log_admin_event(
        session,
        admin_info,
        action="user_ban",
        entity_type="user",
        entity_id=user.id,
        metadata={"reason": payload.reason},
    )
    await session.commit()
    return {"user_id": user.id, "is_banned": user.is_banned, "ban_reason": user.ban_reason}


@router.post("/users/{user_id}/unban")
async def unban_user(
    user_id: int,
    admin_info: dict = Depends(get_admin_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")
    user.is_banned = False
    user.ban_reason = None
    await _log_admin_event(
        session,
        admin_info,
        action="user_unban",
        entity_type="user",
        entity_id=user.id,
    )
    await session.commit()
    return {"user_id": user.id, "is_banned": user.is_banned}


@router.post("/users/{user_id}/premium/grant")
async def grant_premium(
    user_id: int,
    payload: PremiumGrantRequest,
    admin_info: dict = Depends(get_admin_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")
    premium_until = await apply_premium_days(
        session,
        user_id,
        payload.days,
        payload.reason,
    )
    await _log_admin_event(
        session,
        admin_info,
        action="premium_granted",
        entity_type="user_premium",
        entity_id=user_id,
        metadata={"days": payload.days, "reason": payload.reason},
    )
    await session.commit()
    logger.info(
        "Admin premium grant: user_id=%s days=%s reason=%s",
        user_id,
        payload.days,
        payload.reason,
    )
    return {"user_id": user_id, "premium_until": premium_until}


@router.post("/users/{user_id}/premium/revoke")
async def revoke_premium(
    user_id: int,
    payload: PremiumRevokeRequest,
    admin_info: dict = Depends(get_admin_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")
    now = datetime.now(timezone.utc)
    premium = await session.get(UserPremium, user_id)
    if premium:
        premium.premium_until = now
    else:
        premium = UserPremium(user_id=user_id, premium_until=now)
        session.add(premium)
    await _log_admin_event(
        session,
        admin_info,
        action="premium_revoked",
        entity_type="user_premium",
        entity_id=user_id,
        metadata={"reason": payload.reason},
    )
    await session.commit()
    logger.info("Admin premium revoke: user_id=%s reason=%s", user_id, payload.reason)
    return {"user_id": user_id, "premium_until": premium.premium_until}


@router.get("/referrals")
async def list_referrals(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: dict = Depends(get_admin_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    referrer_alias = User.__table__.alias("referrer")
    referred_alias = User.__table__.alias("referred")
    query = (
        select(
            Referral,
            referrer_alias.c.tg_user_id.label("referrer_tg_user_id"),
            referrer_alias.c.username.label("referrer_username"),
            referred_alias.c.tg_user_id.label("referred_tg_user_id"),
            referred_alias.c.username.label("referred_username"),
        )
        .join(referrer_alias, Referral.referrer_user_id == referrer_alias.c.id)
        .join(referred_alias, Referral.referred_user_id == referred_alias.c.id)
    )
    total_result = await session.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar_one()
    result = await session.execute(query.order_by(Referral.id.desc()).limit(limit).offset(offset))
    rows = result.all()
    items = []
    for row in rows:
        referral = row[0]
        items.append(
            {
                "id": referral.id,
                "referrer_user_id": referral.referrer_user_id,
                "referrer_tg_user_id": row.referrer_tg_user_id,
                "referrer_username": row.referrer_username,
                "referred_user_id": referral.referred_user_id,
                "referred_tg_user_id": row.referred_tg_user_id,
                "referred_username": row.referred_username,
                "created_at": referral.created_at,
            }
        )
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/referral_rewards")
async def list_referral_rewards(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: dict = Depends(get_admin_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    referrer_alias = User.__table__.alias("referrer")
    referred_alias = User.__table__.alias("referred")
    query = (
        select(
            ReferralReward,
            referrer_alias.c.tg_user_id.label("referrer_tg_user_id"),
            referrer_alias.c.username.label("referrer_username"),
            referred_alias.c.tg_user_id.label("referred_tg_user_id"),
            referred_alias.c.username.label("referred_username"),
        )
        .join(referrer_alias, ReferralReward.referrer_user_id == referrer_alias.c.id)
        .join(referred_alias, ReferralReward.referred_user_id == referred_alias.c.id)
    )
    total_result = await session.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar_one()
    result = await session.execute(
        query.order_by(ReferralReward.id.desc()).limit(limit).offset(offset)
    )
    rows = result.all()
    items = []
    for row in rows:
        reward = row[0]
        items.append(
            {
                "id": reward.id,
                "referrer_user_id": reward.referrer_user_id,
                "referrer_tg_user_id": row.referrer_tg_user_id,
                "referrer_username": row.referrer_username,
                "referred_user_id": reward.referred_user_id,
                "referred_tg_user_id": row.referred_tg_user_id,
                "referred_username": row.referred_username,
                "reward_days": reward.reward_days,
                "reason": reward.reason,
                "applied": reward.applied,
                "applied_at": reward.applied_at,
                "created_at": reward.created_at,
            }
        )
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }
