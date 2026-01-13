from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AudioTrack, MediaVariant, Quality, UserState

logger = logging.getLogger("kina.api.watch_resolver")


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

    variants = await _load_variants(session=session, base_filters=base_filters)
    _log_variant_diagnostics(
        user_id=user_id,
        title_id=title_id,
        episode_id=episode_id,
        requested_audio_id=requested_audio_id,
        requested_quality_id=requested_quality_id,
        resolved_audio_id=resolved_audio_id,
        resolved_quality_id=resolved_quality_id,
        variants=variants,
    )

    if resolved_audio_id is None or resolved_quality_id is None:
        best_variant = await _find_best_variant(
            session=session,
            variants=variants,
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

    variant = await _find_variant_with_file(
        variants=variants,
        audio_id=resolved_audio_id,
        quality_id=resolved_quality_id,
    )
    if not variant:
        fallback_variant = await _find_best_variant(
            session=session,
            variants=variants,
            required_audio_id=None,
            required_quality_id=None,
            preferred_audio_id=resolved_audio_id,
            preferred_quality_id=resolved_quality_id,
        )
        if fallback_variant is None:
            raise ResolveVariantError(await _build_available_payload(session, title_id, episode_id))
        logger.info(
            "watch resolve fallback",
            extra={
                "action": "watch_resolve_fallback",
                "user_id": user_id,
                "title_id": title_id,
                "episode_id": episode_id,
                "requested_audio_id": resolved_audio_id,
                "requested_quality_id": resolved_quality_id,
                "variant_id": fallback_variant.id,
                "variant_audio_id": fallback_variant.audio_id,
                "variant_quality_id": fallback_variant.quality_id,
            },
        )
        return ResolveResult(
            variant_id=fallback_variant.id,
            audio_id=fallback_variant.audio_id,
            quality_id=fallback_variant.quality_id,
        )

    return ResolveResult(
        variant_id=variant.id,
        audio_id=resolved_audio_id,
        quality_id=resolved_quality_id,
    )


def _find_variant_with_file(
    *,
    variants: list[MediaVariant],
    audio_id: int,
    quality_id: int,
) -> MediaVariant | None:
    for variant in variants:
        if (
            variant.audio_id == audio_id
            and variant.quality_id == quality_id
            and _variant_has_file(variant)
        ):
            return variant
    return None


async def _find_best_variant(
    *,
    session: AsyncSession,
    variants: list[MediaVariant],
    required_audio_id: int | None,
    required_quality_id: int | None,
    preferred_audio_id: int | None,
    preferred_quality_id: int | None,
) -> MediaVariant | None:
    if not variants:
        return None
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
            MediaVariant.id.in_([variant.id for variant in variants]),
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
            MediaVariant.telegram_file_id.is_not(None),
            MediaVariant.telegram_file_id != "",
            MediaVariant.storage_message_id.is_not(None),
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
        if item.status == "ready" and _variant_has_file(item)
    ]
    variants_with_file = [
        item for item in available_variants if _variant_has_file(item)
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
            "with_file": len(variants_with_file),
        },
        available_variants=variants_payload,
        available_audio_ids=audio_ids,
        available_quality_ids=quality_ids,
    )


def _variant_has_file(variant: MediaVariant) -> bool:
    return bool(variant.telegram_file_id) and variant.storage_message_id is not None


async def _load_variants(
    *,
    session: AsyncSession,
    base_filters: list,
) -> list[MediaVariant]:
    variant_query = select(MediaVariant).where(*base_filters)
    variant_result = await session.execute(variant_query)
    return variant_result.scalars().all()


def _log_variant_diagnostics(
    *,
    user_id: int,
    title_id: int,
    episode_id: int | None,
    requested_audio_id: int | None,
    requested_quality_id: int | None,
    resolved_audio_id: int | None,
    resolved_quality_id: int | None,
    variants: list[MediaVariant],
) -> None:
    def _match_audio_quality(
        variant: MediaVariant, audio: int | None, quality: int | None
    ) -> bool:
        if audio is not None and variant.audio_id != audio:
            return False
        if quality is not None and variant.quality_id != quality:
            return False
        return True

    with_file = [item for item in variants if _variant_has_file(item)]
    match_requested = [
        item for item in variants if _match_audio_quality(item, requested_audio_id, requested_quality_id)
    ]
    match_resolved = [
        item for item in variants if _match_audio_quality(item, resolved_audio_id, resolved_quality_id)
    ]
    match_resolved_with_file = [
        item for item in match_resolved if _variant_has_file(item)
    ]
    candidates = [
        {
            "variant_id": item.id,
            "status": item.status,
            "audio_id": item.audio_id,
            "quality_id": item.quality_id,
            "has_file": _variant_has_file(item),
        }
        for item in variants
    ]
    logger.info(
        "watch resolve diagnostics",
        extra={
            "action": "watch_resolve_diagnostics",
            "user_id": user_id,
            "title_id": title_id,
            "episode_id": episode_id,
            "requested_audio_id": requested_audio_id,
            "requested_quality_id": requested_quality_id,
            "resolved_audio_id": resolved_audio_id,
            "resolved_quality_id": resolved_quality_id,
            "counts": {
                "total": len(variants),
                "with_file": len(with_file),
                "match_requested": len(match_requested),
                "match_resolved": len(match_resolved),
                "match_resolved_with_file": len(match_resolved_with_file),
                "status_ready": len([item for item in variants if item.status == "ready"]),
            },
            "candidates": candidates,
        },
    )
