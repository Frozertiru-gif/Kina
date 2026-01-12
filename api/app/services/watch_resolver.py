from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AudioTrack, MediaVariant, Quality, UserState


@dataclass(frozen=True)
class ResolveResult:
    variant_id: int
    audio_id: int
    quality_id: int


@dataclass(frozen=True)
class ResolveNotFound:
    error: str
    counts: dict
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
    preferred_audio_id = state.preferred_audio_id if state else None
    preferred_quality_id = state.preferred_quality_id if state else None

    requested_audio_id = audio_id
    requested_quality_id = quality_id
    resolved_audio_id = audio_id or preferred_audio_id
    resolved_quality_id = quality_id or preferred_quality_id

    base_filters = [MediaVariant.title_id == title_id]
    if episode_id is None:
        base_filters.append(MediaVariant.episode_id.is_(None))
    else:
        base_filters.append(MediaVariant.episode_id == episode_id)

    if resolved_audio_id is None or resolved_quality_id is None:
        best_variant = await _find_best_variant(
            session=session,
            base_filters=base_filters,
            required_audio_id=requested_audio_id,
            required_quality_id=requested_quality_id,
            preferred_audio_id=resolved_audio_id,
            preferred_quality_id=resolved_quality_id,
        )
        if best_variant is None:
            raise ResolveVariantError(await _build_available_payload(session, title_id, episode_id))
        return ResolveResult(
            variant_id=best_variant.id,
            audio_id=best_variant.audio_id,
            quality_id=best_variant.quality_id,
        )

    variant = await _find_variant_with_status(
        session=session,
        base_filters=base_filters,
        audio_id=resolved_audio_id,
        quality_id=resolved_quality_id,
    )
    if not variant:
        raise ResolveVariantError(await _build_available_payload(session, title_id, episode_id))

    return ResolveResult(
        variant_id=variant.id,
        audio_id=resolved_audio_id,
        quality_id=resolved_quality_id,
    )


async def _find_variant_with_status(
    *,
    session: AsyncSession,
    base_filters: list,
    audio_id: int,
    quality_id: int,
) -> MediaVariant | None:
    variant_query = select(MediaVariant).where(
        *base_filters,
        MediaVariant.audio_id == audio_id,
        MediaVariant.quality_id == quality_id,
        MediaVariant.status == "ready",
        MediaVariant.telegram_file_id.is_not(None),
        MediaVariant.telegram_file_id != "",
    )
    variant_result = await session.execute(variant_query)
    variant = variant_result.scalar_one_or_none()
    if variant:
        return variant
    return None


async def _find_best_variant(
    *,
    session: AsyncSession,
    base_filters: list,
    required_audio_id: int | None,
    required_quality_id: int | None,
    preferred_audio_id: int | None,
    preferred_quality_id: int | None,
) -> MediaVariant | None:
    order_clauses = []
    if preferred_audio_id is not None:
        order_clauses.append((MediaVariant.audio_id == preferred_audio_id).desc())
    else:
        order_clauses.append(AudioTrack.id.asc())
    if preferred_quality_id is not None:
        order_clauses.append((MediaVariant.quality_id == preferred_quality_id).desc())
    order_clauses.append(Quality.height.desc())
    order_clauses.append(MediaVariant.id.asc())
    variant_query = (
        select(MediaVariant)
        .join(AudioTrack, AudioTrack.id == MediaVariant.audio_id)
        .join(Quality, Quality.id == MediaVariant.quality_id)
        .where(
            *base_filters,
            *(
                [MediaVariant.audio_id == required_audio_id]
                if required_audio_id is not None
                else []
            ),
            *(
                [MediaVariant.quality_id == required_quality_id]
                if required_quality_id is not None
                else []
            ),
            MediaVariant.status == "ready",
            MediaVariant.telegram_file_id.is_not(None),
            MediaVariant.telegram_file_id != "",
            AudioTrack.is_active.is_(True),
            Quality.is_active.is_(True),
        )
        .order_by(*order_clauses)
        .limit(1)
    )
    variant_result = await session.execute(variant_query)
    variant = variant_result.scalar_one_or_none()
    if variant:
        return variant
    return None


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
    ready_variants = [item for item in available_variants if item.status == "ready"]
    ready_with_file = [
        item
        for item in available_variants
        if item.status == "ready" and item.telegram_file_id not in (None, "")
    ]
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
        error="no_ready_variant_with_file",
        counts={
            "total": len(available_variants),
            "ready": len(ready_variants),
            "ready_with_file": len(ready_with_file),
        },
        available_variants=variants_payload,
        available_audio_ids=audio_ids,
        available_quality_ids=quality_ids,
    )
