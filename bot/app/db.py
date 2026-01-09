from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@dataclass(frozen=True)
class TitleInfo:
    id: int
    name: str
    type: str


@dataclass(frozen=True)
class EpisodeInfo:
    id: int
    title_id: int
    season_id: int
    season_number: int
    episode_number: int


@dataclass(frozen=True)
class VariantInfo:
    id: int
    title_id: int
    episode_id: int | None
    audio_id: int
    quality_id: int
    telegram_file_id: str | None


@dataclass(frozen=True)
class UserStateInfo:
    user_id: int
    active_chat_id: int | None
    active_message_id: int | None
    active_title_id: int | None
    active_episode_id: int | None
    active_variant_id: int | None


def create_session_maker(database_url: str) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_or_create_user_id(session: AsyncSession, tg_user_id: int) -> int:
    result = await session.execute(
        text("SELECT id FROM users WHERE tg_user_id = :tg_user_id"),
        {"tg_user_id": tg_user_id},
    )
    user_id = result.scalar_one_or_none()
    if user_id:
        return user_id
    insert_result = await session.execute(
        text("INSERT INTO users (tg_user_id) VALUES (:tg_user_id) RETURNING id"),
        {"tg_user_id": tg_user_id},
    )
    await session.commit()
    return int(insert_result.scalar_one())


async def get_user_state(session: AsyncSession, tg_user_id: int) -> UserStateInfo:
    user_id = await get_or_create_user_id(session, tg_user_id)
    result = await session.execute(
        text(
            """
            SELECT active_chat_id, active_message_id, active_title_id, active_episode_id, active_variant_id
            FROM user_state
            WHERE user_id = :user_id
            """
        ),
        {"user_id": user_id},
    )
    row = result.mappings().one_or_none()
    if row is None:
        await session.execute(
            text("INSERT INTO user_state (user_id) VALUES (:user_id)"),
            {"user_id": user_id},
        )
        await session.commit()
        return UserStateInfo(
            user_id=user_id,
            active_chat_id=None,
            active_message_id=None,
            active_title_id=None,
            active_episode_id=None,
            active_variant_id=None,
        )
    return UserStateInfo(
        user_id=user_id,
        active_chat_id=row["active_chat_id"],
        active_message_id=row["active_message_id"],
        active_title_id=row["active_title_id"],
        active_episode_id=row["active_episode_id"],
        active_variant_id=row["active_variant_id"],
    )


async def set_active_message(
    session: AsyncSession,
    tg_user_id: int,
    chat_id: int,
    message_id: int,
    title_id: int | None,
    episode_id: int | None,
    variant_id: int | None,
) -> None:
    user_id = await get_or_create_user_id(session, tg_user_id)
    await session.execute(
        text(
            """
            INSERT INTO user_state (
                user_id, active_chat_id, active_message_id, active_title_id, active_episode_id, active_variant_id
            )
            VALUES (:user_id, :chat_id, :message_id, :title_id, :episode_id, :variant_id)
            ON CONFLICT (user_id) DO UPDATE SET
                active_chat_id = EXCLUDED.active_chat_id,
                active_message_id = EXCLUDED.active_message_id,
                active_title_id = EXCLUDED.active_title_id,
                active_episode_id = EXCLUDED.active_episode_id,
                active_variant_id = EXCLUDED.active_variant_id,
                updated_at = now()
            """
        ),
        {
            "user_id": user_id,
            "chat_id": chat_id,
            "message_id": message_id,
            "title_id": title_id,
            "episode_id": episode_id,
            "variant_id": variant_id,
        },
    )
    await session.commit()


async def fetch_title(session: AsyncSession, title_id: int) -> TitleInfo | None:
    result = await session.execute(
        text("SELECT id, name, type FROM titles WHERE id = :title_id"),
        {"title_id": title_id},
    )
    row = result.mappings().one_or_none()
    if row is None:
        return None
    return TitleInfo(id=row["id"], name=row["name"], type=row["type"])


async def fetch_episode(session: AsyncSession, episode_id: int) -> EpisodeInfo | None:
    result = await session.execute(
        text(
            """
            SELECT episodes.id, episodes.title_id, episodes.season_id, seasons.season_number, episodes.episode_number
            FROM episodes
            JOIN seasons ON seasons.id = episodes.season_id
            WHERE episodes.id = :episode_id
            """
        ),
        {"episode_id": episode_id},
    )
    row = result.mappings().one_or_none()
    if row is None:
        return None
    return EpisodeInfo(
        id=row["id"],
        title_id=row["title_id"],
        season_id=row["season_id"],
        season_number=row["season_number"],
        episode_number=row["episode_number"],
    )


async def fetch_variant(session: AsyncSession, variant_id: int) -> VariantInfo | None:
    result = await session.execute(
        text(
            """
            SELECT id, title_id, episode_id, audio_id, quality_id, telegram_file_id
            FROM media_variants
            WHERE id = :variant_id
            """
        ),
        {"variant_id": variant_id},
    )
    row = result.mappings().one_or_none()
    if row is None:
        return None
    return VariantInfo(
        id=row["id"],
        title_id=row["title_id"],
        episode_id=row["episode_id"],
        audio_id=row["audio_id"],
        quality_id=row["quality_id"],
        telegram_file_id=row["telegram_file_id"],
    )


async def fetch_variant_by_selection(
    session: AsyncSession,
    title_id: int,
    episode_id: int | None,
    audio_id: int,
    quality_id: int,
) -> VariantInfo | None:
    result = await session.execute(
        text(
            """
            SELECT id, title_id, episode_id, audio_id, quality_id, telegram_file_id
            FROM media_variants
            WHERE title_id = :title_id
              AND audio_id = :audio_id
              AND quality_id = :quality_id
              AND (:episode_id IS NULL AND episode_id IS NULL OR episode_id = :episode_id)
              AND status IN ('pending', 'ready')
            ORDER BY id
            LIMIT 1
            """
        ),
        {
            "title_id": title_id,
            "episode_id": episode_id,
            "audio_id": audio_id,
            "quality_id": quality_id,
        },
    )
    row = result.mappings().one_or_none()
    if row is None:
        return None
    return VariantInfo(
        id=row["id"],
        title_id=row["title_id"],
        episode_id=row["episode_id"],
        audio_id=row["audio_id"],
        quality_id=row["quality_id"],
        telegram_file_id=row["telegram_file_id"],
    )


async def fetch_default_variant(
    session: AsyncSession,
    title_id: int,
    episode_id: int | None,
) -> VariantInfo | None:
    result = await session.execute(
        text(
            """
            SELECT id, title_id, episode_id, audio_id, quality_id, telegram_file_id
            FROM media_variants
            WHERE title_id = :title_id
              AND (:episode_id IS NULL AND episode_id IS NULL OR episode_id = :episode_id)
              AND status IN ('pending', 'ready')
            ORDER BY id
            LIMIT 1
            """
        ),
        {"title_id": title_id, "episode_id": episode_id},
    )
    row = result.mappings().one_or_none()
    if row is None:
        return None
    return VariantInfo(
        id=row["id"],
        title_id=row["title_id"],
        episode_id=row["episode_id"],
        audio_id=row["audio_id"],
        quality_id=row["quality_id"],
        telegram_file_id=row["telegram_file_id"],
    )


async def fetch_adjacent_episode(
    session: AsyncSession,
    episode_id: int,
    direction: str,
) -> EpisodeInfo | None:
    episode = await fetch_episode(session, episode_id)
    if not episode:
        return None
    comparator = "<" if direction == "prev" else ">"
    ordering = "DESC" if direction == "prev" else "ASC"
    result = await session.execute(
        text(
            f"""
            SELECT episodes.id, episodes.title_id, episodes.season_id, seasons.season_number, episodes.episode_number
            FROM episodes
            JOIN seasons ON seasons.id = episodes.season_id
            WHERE episodes.season_id = :season_id
              AND episodes.episode_number {comparator} :episode_number
            ORDER BY episodes.episode_number {ordering}
            LIMIT 1
            """
        ),
        {"season_id": episode.season_id, "episode_number": episode.episode_number},
    )
    row = result.mappings().one_or_none()
    if row is None:
        return None
    return EpisodeInfo(
        id=row["id"],
        title_id=row["title_id"],
        season_id=row["season_id"],
        season_number=row["season_number"],
        episode_number=row["episode_number"],
    )


async def fetch_audio_options(session: AsyncSession, title_id: int, episode_id: int | None) -> list[tuple]:
    result = await session.execute(
        text(
            """
            SELECT DISTINCT audio_tracks.id AS audio_id, audio_tracks.name AS audio_name
            FROM media_variants
            JOIN audio_tracks ON audio_tracks.id = media_variants.audio_id
            WHERE media_variants.title_id = :title_id
              AND (:episode_id IS NULL AND media_variants.episode_id IS NULL OR media_variants.episode_id = :episode_id)
            ORDER BY audio_tracks.name
            """
        ),
        {"title_id": title_id, "episode_id": episode_id},
    )
    return [(row["audio_id"], row["audio_name"]) for row in result.mappings().all()]


async def fetch_quality_options(session: AsyncSession, title_id: int, episode_id: int | None) -> list[tuple]:
    result = await session.execute(
        text(
            """
            SELECT DISTINCT qualities.id AS quality_id, qualities.name AS quality_name
            FROM media_variants
            JOIN qualities ON qualities.id = media_variants.quality_id
            WHERE media_variants.title_id = :title_id
              AND (:episode_id IS NULL AND media_variants.episode_id IS NULL OR media_variants.episode_id = :episode_id)
            ORDER BY qualities.height DESC
            """
        ),
        {"title_id": title_id, "episode_id": episode_id},
    )
    return [(row["quality_id"], row["quality_name"]) for row in result.mappings().all()]
