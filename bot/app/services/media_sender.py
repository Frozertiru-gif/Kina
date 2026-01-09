import logging

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app import keyboards
from app.db import (
    EpisodeInfo,
    TitleInfo,
    VariantInfo,
    fetch_episode,
    fetch_title,
    fetch_variant,
)
from app.services.message_state import demote_previous_message, mark_active_message

logger = logging.getLogger("kina.bot.media_sender")


def build_card_text(title: TitleInfo, episode: EpisodeInfo | None) -> str:
    if episode:
        return f"{title.name}\nS{episode.season_number}E{episode.episode_number}"
    return title.name


async def send_watch_card(
    bot: Bot,
    session: AsyncSession,
    tg_user_id: int,
    title_id: int,
    episode_id: int | None,
    variant_id: int | None,
    mode: str,
) -> None:
    title = await fetch_title(session, title_id)
    if not title:
        logger.warning("Title not found: %s", title_id)
        return
    episode = await fetch_episode(session, episode_id) if episode_id else None
    await demote_previous_message(bot, session, tg_user_id)
    text = build_card_text(title, episode)
    if mode:
        text = f"{text}\nРежим: {mode}"
    keyboard = _build_keyboard(title, episode, variant_id)
    message = await bot.send_message(chat_id=tg_user_id, text=text, reply_markup=keyboard)
    await mark_active_message(
        session,
        tg_user_id=tg_user_id,
        chat_id=message.chat.id,
        message_id=message.message_id,
        title_id=title_id,
        episode_id=episode_id,
        variant_id=variant_id,
    )


async def send_video_by_variant(
    bot: Bot,
    session: AsyncSession,
    tg_user_id: int,
    variant_id: int,
) -> None:
    variant = await fetch_variant(session, variant_id)
    if not variant:
        logger.warning("Variant not found: %s", variant_id)
        return
    title = await fetch_title(session, variant.title_id)
    if not title:
        logger.warning("Title not found for variant: %s", variant_id)
        return
    episode = await fetch_episode(session, variant.episode_id) if variant.episode_id else None
    await demote_previous_message(bot, session, tg_user_id)
    if not variant.telegram_file_id:
        message = await bot.send_message(
            chat_id=tg_user_id,
            text="Видео ещё загружается",
            reply_markup=keyboards.refresh_keyboard(variant_id),
        )
        await mark_active_message(
            session,
            tg_user_id=tg_user_id,
            chat_id=message.chat.id,
            message_id=message.message_id,
            title_id=variant.title_id,
            episode_id=variant.episode_id,
            variant_id=variant.id,
        )
        return
    keyboard = _build_keyboard(title, episode, variant.id)
    message = await bot.send_video(
        chat_id=tg_user_id,
        video=variant.telegram_file_id,
        caption=build_card_text(title, episode),
        reply_markup=keyboard,
    )
    await mark_active_message(
        session,
        tg_user_id=tg_user_id,
        chat_id=message.chat.id,
        message_id=message.message_id,
        title_id=variant.title_id,
        episode_id=variant.episode_id,
        variant_id=variant.id,
    )


def _build_keyboard(
    title: TitleInfo,
    episode: EpisodeInfo | None,
    variant_id: int | None,
):
    if title.type == "series" and episode:
        return keyboards.series_keyboard(title.id, episode.id)
    return keyboards.movie_keyboard(title.id)
