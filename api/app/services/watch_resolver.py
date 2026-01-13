from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MediaVariant, UserState

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
    ready_variants = [item for item in variants if _variant_has_file(item)]
    _log_variant_diagnostics(
        user_id=user_id,
        title_id=title_id,
        episode_id=episode_id,
        requested_audio_id=requested_audio_id,
        requested_quality_id=requested_quality_id,
        resolved_audio_id=resolved_audio_id,
        resolved_quality_id=resolved_quality_id,
        variants=variants,
        ready_variants=ready_variants,
    )

    exact_variant = _find_exact_ready_variant(
        ready_variants=ready_variants,
        audio_id=resolved_audio_id,
        quality_id=resolved_quality_id,
    )
    if exact_variant:
        logger.info(
            "watch resolve success",
            extra={
                "action": "watch_resolve",
                "user_id": user_id,
                "title_id": title_id,
                "episode_id": episode_id,
                "variant_id": exact_variant.id,
                "variant_audio_id": exact_variant.audio_id,
                "variant_quality_id": exact_variant.quality_id,
                "requested_audio_id": requested_audio_id,
                "requested_quality_id": requested_quality_id,
                "resolved_audio_id": resolved_audio_id,
                "resolved_quality_id": resolved_quality_id,
                "fallback": False,
            },
        )
        return ResolveResult(
            variant_id=exact_variant.id,
            audio_id=exact_variant.audio_id,
            quality_id=exact_variant.quality_id,
        )

    fallback_variant = _select_fallback_variant(
        ready_variants=ready_variants,
        resolved_audio_id=resolved_audio_id,
        resolved_quality_id=resolved_quality_id,
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
            "requested_audio_id": requested_audio_id,
            "requested_quality_id": requested_quality_id,
            "resolved_audio_id": resolved_audio_id,
            "resolved_quality_id": resolved_quality_id,
            "variant_id": fallback_variant.id,
            "variant_audio_id": fallback_variant.audio_id,
            "variant_quality_id": fallback_variant.quality_id,
            "fallback_reason": _fallback_reason(
                resolved_audio_id=resolved_audio_id,
                resolved_quality_id=resolved_quality_id,
            ),
        },
    )
    logger.info(
        "watch resolve success",
        extra={
            "action": "watch_resolve",
            "user_id": user_id,
            "title_id": title_id,
            "episode_id": episode_id,
            "variant_id": fallback_variant.id,
            "variant_audio_id": fallback_variant.audio_id,
            "variant_quality_id": fallback_variant.quality_id,
            "requested_audio_id": requested_audio_id,
            "requested_quality_id": requested_quality_id,
            "resolved_audio_id": resolved_audio_id,
            "resolved_quality_id": resolved_quality_id,
            "fallback": True,
        },
    )
    return ResolveResult(
        variant_id=fallback_variant.id,
        audio_id=fallback_variant.audio_id,
        quality_id=fallback_variant.quality_id,
    )


def _find_exact_ready_variant(
    *,
    ready_variants: list[MediaVariant],
    audio_id: int | None,
    quality_id: int | None,
) -> MediaVariant | None:
    if audio_id is None or quality_id is None:
        return None
    for variant in ready_variants:
        if variant.audio_id == audio_id and variant.quality_id == quality_id:
            return variant
    return None


def _select_fallback_variant(
    *,
    ready_variants: list[MediaVariant],
    resolved_audio_id: int | None,
    resolved_quality_id: int | None,
) -> MediaVariant | None:
    if not ready_variants:
        return None

    def _sort_key(variant: MediaVariant) -> tuple:
        audio_match = resolved_audio_id is not None and variant.audio_id == resolved_audio_id
        quality_match = resolved_quality_id is not None and variant.quality_id == resolved_quality_id
        return (
            0 if audio_match else 1,
            0 if quality_match else 1,
            variant.id,
        )

    return sorted(ready_variants, key=_sort_key)[0]


def _fallback_reason(*, resolved_audio_id: int | None, resolved_quality_id: int | None) -> str:
    if resolved_audio_id is not None and resolved_quality_id is not None:
        return "no_exact_match_prefer_audio_then_quality"
    if resolved_audio_id is not None:
        return "no_exact_match_prefer_audio"
    if resolved_quality_id is not None:
        return "no_exact_match_prefer_quality"
    return "no_exact_match_pick_first"


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
    variants_with_file_id = [item for item in available_variants if _variant_has_file_id(item)]
    variants_with_storage_message_id = [
        item for item in available_variants if _variant_has_storage_message(item)
    ]
    ready_with_file = [item for item in available_variants if _variant_has_file(item)]
    audio_ids = sorted({item.audio_id for item in available_variants})
    quality_ids = sorted({item.quality_id for item in available_variants})
    variants_payload = [
        {
            "audio_id": item.audio_id,
            "quality_id": item.quality_id,
            "variant_id": item.id,
            "has_file_id": _variant_has_file_id(item),
            "has_storage_msg": _variant_has_storage_message(item),
        }
        for item in available_variants
    ]
    return ResolveNotFound(
        error="no_ready_variant_with_file",
        counts={
            "total": len(available_variants),
            "with_file_id": len(variants_with_file_id),
            "with_storage_message_id": len(variants_with_storage_message_id),
            "ready_with_file": len(ready_with_file),
        },
        available_variants=variants_payload,
        available_audio_ids=audio_ids,
        available_quality_ids=quality_ids,
    )


def _variant_has_file(variant: MediaVariant) -> bool:
    return _variant_has_file_id(variant) and _variant_has_storage_message(variant)


def _variant_has_file_id(variant: MediaVariant) -> bool:
    return bool(variant.telegram_file_id)


def _variant_has_storage_message(variant: MediaVariant) -> bool:
    return variant.storage_message_id is not None


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
    ready_variants: list[MediaVariant],
) -> None:
    def _match_audio_quality(
        variant: MediaVariant, audio: int | None, quality: int | None
    ) -> bool:
        if audio is not None and variant.audio_id != audio:
            return False
        if quality is not None and variant.quality_id != quality:
            return False
        return True

    with_file_id = [item for item in variants if _variant_has_file_id(item)]
    with_storage_message_id = [item for item in variants if _variant_has_storage_message(item)]
    match_requested = [
        item for item in variants if _match_audio_quality(item, requested_audio_id, requested_quality_id)
    ]
    match_resolved = [
        item for item in variants if _match_audio_quality(item, resolved_audio_id, resolved_quality_id)
    ]
    match_resolved_with_file = [item for item in match_resolved if _variant_has_file(item)]
    candidates = [
        {
            "variant_id": item.id,
            "status": item.status,
            "audio_id": item.audio_id,
            "quality_id": item.quality_id,
            "has_file_id": _variant_has_file_id(item),
            "has_storage_msg": _variant_has_storage_message(item),
            "ready_by_canonical": _variant_has_file(item),
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
                "with_file_id": len(with_file_id),
                "with_storage_message_id": len(with_storage_message_id),
                "ready_by_canonical": len(ready_variants),
                "match_requested": len(match_requested),
                "match_resolved": len(match_resolved),
                "match_resolved_with_file": len(match_resolved_with_file),
            },
            "candidates": candidates,
        },
    )
