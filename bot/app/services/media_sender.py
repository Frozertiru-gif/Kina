import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy.ext.asyncio import AsyncSession

from app import keyboards
from app.db import (
    EpisodeInfo,
    TitleInfo,
    VariantInfo,
    fetch_episode,
    fetch_premium_until,
    fetch_title,
    fetch_variant,
    set_user_preferences,
)
from app.services.message_state import demote_previous_message, mark_active_message

logger = logging.getLogger("kina.bot.media_sender")


def build_card_text(
    title: TitleInfo,
    episode: EpisodeInfo | None,
    variant: VariantInfo | None,
    premium_until: str | None,
    mode: str | None = None,
) -> str:
    if episode:
        episode_name = f" — {episode.name}" if episode.name else ""
        header = f"{title.name}\nS{episode.season_number}E{episode.episode_number}{episode_name}"
    else:
        header = title.name

    lines = [header]
    if variant and variant.audio_name and variant.quality_name:
        lines.append(f"{variant.audio_name} · {variant.quality_name}")
    if premium_until:
        premium_label = (
            premium_until.strftime("%d.%m.%Y")
            if hasattr(premium_until, "strftime")
            else str(premium_until)
        )
        lines.append(f"Premium активен до {premium_label}")
    if mode == "ad_gate":
        lines.append("Требуется реклама")
    return "\n".join(lines)


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
    variant = await fetch_variant(session, variant_id) if variant_id else None
    premium_until = await fetch_premium_until(session, tg_user_id)
    await demote_previous_message(bot, session, tg_user_id)
    text = build_card_text(title, episode, variant, premium_until, mode)
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
    premium_until = await fetch_premium_until(session, tg_user_id)
    await demote_previous_message(bot, session, tg_user_id)
    if not variant.telegram_file_id or variant.status != "ready":
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
    try:
        message = await bot.send_video(
            chat_id=tg_user_id,
            video=variant.telegram_file_id,
            caption=build_card_text(title, episode, variant, premium_until),
            reply_markup=keyboard,
        )
    except TelegramBadRequest as exc:
        logger.warning(
            "Failed to send video: %s",
            exc,
            extra={
                "action": "send_video_failed",
                "variant_id": variant.id,
                "tg_user_id": tg_user_id,
            },
        )
        await _send_video_error_message(bot, tg_user_id)
        return
    except TelegramForbiddenError as exc:
        logger.warning(
            "Forbidden to send video: %s",
            exc,
            extra={
                "action": "send_video_failed",
                "variant_id": variant.id,
                "tg_user_id": tg_user_id,
            },
        )
        await _send_video_error_message(bot, tg_user_id)
        return
    logger.info(
        "Video sent",
        extra={
            "action": "send_video_ok",
            "variant_id": variant.id,
            "tg_user_id": tg_user_id,
        },
    )
    await set_user_preferences(
        session,
        tg_user_id=tg_user_id,
        preferred_audio_id=variant.audio_id,
        preferred_quality_id=variant.quality_id,
        last_title_id=variant.title_id,
        last_episode_id=variant.episode_id,
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


async def _send_video_error_message(bot: Bot, tg_user_id: int) -> None:
    try:
        await bot.send_message(
            chat_id=tg_user_id,
            text="Не удалось отправить видео. Попробуйте позже или обновите запрос.",
        )
    except TelegramForbiddenError as exc:
        logger.warning(
            "Forbidden to send error message: %s",
            exc,
            extra={
                "action": "send_video_failed_notice",
                "tg_user_id": tg_user_id,
            },
        )
