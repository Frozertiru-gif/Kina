from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AudioTrack, MediaVariant, Quality, UserState


@dataclass(frozen=True)
class ResolveResult:
    variant_id: int
    audio_id: int
    quality_id: int


@dataclass(frozen=True)
class ResolveNotFound:
    available_variants: list[dict]
    available_audio_ids: list[int]
    available_quality_ids: list[int]


class ResolveVariantError(Exception):
    def __init__(self, payload: ResolveNotFound) -> None:
        super().__init__("variant_not_found")
        self.payload = payload


async def resolve_watch_variant(
    session: AsyncSession,
    user_id: int,
    title_id: int,
    episode_id: int | None,
    audio_id: int | None,
    quality_id: int | None,
) -> ResolveResult:
    state = await session.get(UserState, user_id)
    if state is None:
        state = UserState(user_id=user_id)
        session.add(state)
        await session.flush()

    resolved_audio_id = audio_id or state.preferred_audio_id
    resolved_quality_id = quality_id or state.preferred_quality_id

    if resolved_audio_id is None:
        audio_query = (
            select(func.min(MediaVariant.audio_id))
            .join(AudioTrack, AudioTrack.id == MediaVariant.audio_id)
            .where(
                MediaVariant.title_id == title_id,
                AudioTrack.is_active.is_(True),
                MediaVariant.status.in_(["pending", "ready"]),
            )
        )
        if episode_id is None:
            audio_query = audio_query.where(MediaVariant.episode_id.is_(None))
        else:
            audio_query = audio_query.where(MediaVariant.episode_id == episode_id)
        audio_result = await session.execute(audio_query)
        resolved_audio_id = audio_result.scalar_one_or_none()

    if resolved_quality_id is None:
        quality_query = (
            select(Quality.id)
            .join(MediaVariant, MediaVariant.quality_id == Quality.id)
            .where(
                MediaVariant.title_id == title_id,
                Quality.is_active.is_(True),
                MediaVariant.status.in_(["pending", "ready"]),
            )
            .order_by(Quality.height.desc(), Quality.id.asc())
            .limit(1)
        )
        if episode_id is None:
            quality_query = quality_query.where(MediaVariant.episode_id.is_(None))
        else:
            quality_query = quality_query.where(MediaVariant.episode_id == episode_id)
        quality_result = await session.execute(quality_query)
        resolved_quality_id = quality_result.scalar_one_or_none()

    if resolved_audio_id is None or resolved_quality_id is None:
        raise ResolveVariantError(await _build_available_payload(session, title_id, episode_id))

    variant_query = select(MediaVariant).where(
        MediaVariant.audio_id == resolved_audio_id,
        MediaVariant.quality_id == resolved_quality_id,
        MediaVariant.status.in_(["pending", "ready"]),
    )
    if episode_id is None:
        variant_query = variant_query.where(
            MediaVariant.title_id == title_id,
            MediaVariant.episode_id.is_(None),
        )
    else:
        variant_query = variant_query.where(MediaVariant.episode_id == episode_id)
    variant_result = await session.execute(variant_query)
    variant = variant_result.scalar_one_or_none()
    if not variant:
        raise ResolveVariantError(await _build_available_payload(session, title_id, episode_id))

    return ResolveResult(
        variant_id=variant.id,
        audio_id=resolved_audio_id,
        quality_id=resolved_quality_id,
    )


async def _build_available_payload(
    session: AsyncSession,
    title_id: int,
    episode_id: int | None,
) -> ResolveNotFound:
    availability_query = select(MediaVariant).where(MediaVariant.title_id == title_id)
    if episode_id is None:
        availability_query = availability_query.where(MediaVariant.episode_id.is_(None))
    else:
        availability_query = availability_query.where(MediaVariant.episode_id == episode_id)
    availability_result = await session.execute(availability_query)
    available_variants = availability_result.scalars().all()
    audio_ids = sorted({item.audio_id for item in available_variants})
    quality_ids = sorted({item.quality_id for item in available_variants})
    variants_payload = [
        {
            "audio_id": item.audio_id,
            "quality_id": item.quality_id,
            "variant_id": item.id,
        }
        for item in available_variants
    ]
    return ResolveNotFound(
        available_variants=variants_payload,
        available_audio_ids=audio_ids,
        available_quality_ids=quality_ids,
    )
