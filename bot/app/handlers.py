import logging

import httpx
from aiogram import Bot, Router
from aiogram.filters import Command, CommandStart
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import keyboards
from app.db import (
    fetch_audio_options,
    fetch_adjacent_episode,
    fetch_default_variant,
    fetch_episode,
    fetch_quality_options,
    fetch_title,
    fetch_variant,
    fetch_variant_by_selection,
    get_user_state,
)
from app.services.media_sender import send_video_by_variant, send_watch_card
from app.settings import Settings

logger = logging.getLogger("kina.bot.handlers")


def build_router(
    settings: Settings,
    session_maker: async_sessionmaker[AsyncSession],
    redis: Redis,
) -> Router:
    router = Router()

    @router.callback_query()
    async def on_callback(query: CallbackQuery) -> None:
        data = (query.data or "").strip()
        if not data:
            return
        tg_user_id = query.from_user.id
        prefix = _callback_prefix(data)
        if not await _debounce_callback(redis, tg_user_id, prefix):
            await query.answer("Слишком часто")
            return
        if prefix == "reopen":
            if not await _limit_reopen(redis, tg_user_id):
                await query.answer("Слишком часто")
                return
        logger.info(
            "callback received",
            extra={
                "tg_user_id": tg_user_id,
                "action": "callback",
                "request_id": query.id,
            },
        )
        async with session_maker() as session:
            if data == "hide":
                await _handle_hide(query, settings)
            elif data.startswith("reopen:"):
                await _handle_reopen(query, session, data)
            elif data.startswith("refresh:"):
                await _handle_refresh(query, session, data)
            elif data.startswith("toggle_fav:"):
                await _handle_toggle_fav(query, settings, data)
            elif data.startswith("toggle_sub:"):
                await _handle_toggle_sub(query, settings, data)
            elif data.startswith("prev_ep:"):
                await _handle_adjacent_episode(query, session, data, direction="prev")
            elif data.startswith("next_ep:"):
                await _handle_adjacent_episode(query, session, data, direction="next")
            elif data.startswith("aud_menu:"):
                await _handle_audio_menu(query, session, data)
            elif data.startswith("q_menu:"):
                await _handle_quality_menu(query, session, data)
            elif data.startswith("aud_set:"):
                await _handle_audio_set(query, session, settings, data, tg_user_id)
            elif data.startswith("q_set:"):
                await _handle_quality_set(query, session, settings, data, tg_user_id)
            elif data.startswith("back_main:"):
                await _handle_back_main(query, session, data)
            elif data.startswith("episodes:"):
                await query.answer("Откройте список серий в WebApp.", show_alert=True)
            elif data == "open_premium":
                await query.answer("Premium скоро будет доступен.", show_alert=True)
            else:
                await query.answer()

    @router.message(CommandStart())
    async def on_start(message: Message) -> None:
        payload = ""
        if message.text:
            parts = message.text.split(maxsplit=1)
            if len(parts) > 1:
                payload = parts[1].strip()
        referral_code = ""
        if payload.startswith("ref_"):
            referral_code = payload.replace("ref_", "", 1)
        if referral_code:
            response = await _post_service_json(
                settings,
                "/api/internal/referral/apply",
                {
                    "tg_user_id": message.from_user.id,
                    "code": referral_code,
                    "username": message.from_user.username,
                    "first_name": message.from_user.first_name,
                    "language_code": message.from_user.language_code,
                },
            )
            if response and response.get("applied"):
                await message.answer("Реферальный код применён. Спасибо!")
            else:
                await message.answer("Реферальный код не применён.")
        else:
            await message.answer("Добро пожаловать в Kina!")
        logger.info(
            "start handled",
            extra={
                "tg_user_id": message.from_user.id,
                "action": "start",
                "request_id": str(message.message_id),
            },
        )

    @router.message(Command("ref"))
    async def on_ref(message: Message) -> None:
        response = await _post_service_json(
            settings,
            "/api/internal/referral/code",
            {
                "tg_user_id": message.from_user.id,
                "username": message.from_user.username,
                "first_name": message.from_user.first_name,
                "language_code": message.from_user.language_code,
            },
        )
        if not response:
            await message.answer("Не удалось получить реферальный код.")
            return
        code = response.get("code")
        link = response.get("link")
        await message.answer(
            "Ваш реферальный код:\n"
            f"{code}\n\n"
            "Поделитесь ссылкой:\n"
            f"{link}"
        )
        logger.info(
            "ref handled",
            extra={
                "tg_user_id": message.from_user.id,
                "action": "ref",
                "request_id": str(message.message_id),
            },
        )

    return router


def _callback_prefix(data: str) -> str:
    return data.split(":", 1)[0]


async def _debounce_callback(redis: Redis, tg_user_id: int, prefix: str) -> bool:
    key = f"cb:{tg_user_id}:{prefix}"
    return bool(await redis.set(key, "1", ex=1, nx=True))


async def _limit_reopen(redis: Redis, tg_user_id: int) -> bool:
    key = f"cb_reopen:{tg_user_id}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 30)
    return count <= 5


async def _handle_hide(query: CallbackQuery, settings: Settings) -> None:
    try:
        await query.message.delete()
    except TelegramBadRequest:
        logger.info("Failed to delete message", exc_info=True)
    await query.answer()


async def _handle_reopen(query: CallbackQuery, session: AsyncSession, data: str) -> None:
    parts = data.split(":")
    title_id = int(parts[1])
    episode_id = int(parts[2]) if len(parts) > 2 else None
    variant = await fetch_default_variant(session, title_id, episode_id)
    await send_watch_card(
        query.bot,
        session,
        tg_user_id=query.from_user.id,
        title_id=title_id,
        episode_id=episode_id,
        variant_id=variant.id if variant else None,
        mode="reopen",
    )
    await query.answer()


async def _handle_refresh(query: CallbackQuery, session: AsyncSession, data: str) -> None:
    variant_id = int(data.split(":")[1])
    await send_video_by_variant(query.bot, session, query.from_user.id, variant_id)
    await query.answer()


async def _handle_toggle_fav(query: CallbackQuery, settings: Settings, data: str) -> None:
    title_id = int(data.split(":")[1])
    await _post_service_json(
        settings,
        "/api/internal/bot/favorites/toggle",
        {"tg_user_id": query.from_user.id, "title_id": title_id},
    )
    await query.answer("Избранное обновлено")


async def _handle_toggle_sub(query: CallbackQuery, settings: Settings, data: str) -> None:
    title_id = int(data.split(":")[1])
    await _post_service_json(
        settings,
        "/api/internal/bot/subscriptions/toggle",
        {"tg_user_id": query.from_user.id, "title_id": title_id},
    )
    await query.answer("Подписка обновлена")


async def _handle_adjacent_episode(
    query: CallbackQuery,
    session: AsyncSession,
    data: str,
    direction: str,
) -> None:
    parts = data.split(":")
    title_id = int(parts[1])
    episode_id = int(parts[2])
    state = await get_user_state(session, query.from_user.id)
    preferred_variant = None
    if state.active_variant_id:
        preferred_variant = await fetch_variant(session, state.active_variant_id)
    next_episode = await fetch_adjacent_episode(session, episode_id, direction)
    if not next_episode:
        await query.answer("Нет доступных серий.", show_alert=True)
        return
    variant = None
    if preferred_variant:
        variant = await fetch_variant_by_selection(
            session,
            title_id=title_id,
            episode_id=next_episode.id,
            audio_id=preferred_variant.audio_id,
            quality_id=preferred_variant.quality_id,
        )
    if not variant:
        variant = await fetch_default_variant(session, title_id, next_episode.id)
    if not variant:
        await query.answer("Нет доступного варианта.", show_alert=True)
        return
    await send_video_by_variant(query.bot, session, query.from_user.id, variant.id)
    await query.answer()


async def _handle_audio_menu(query: CallbackQuery, session: AsyncSession, data: str) -> None:
    parts = data.split(":")
    title_id = int(parts[1])
    episode_id = int(parts[2]) if len(parts) > 2 else None
    audio_options = await fetch_audio_options(session, title_id, episode_id)
    keyboard = keyboards.audio_menu_keyboard(title_id, episode_id, audio_options)
    await query.message.edit_reply_markup(reply_markup=keyboard)
    await query.answer()


async def _handle_quality_menu(query: CallbackQuery, session: AsyncSession, data: str) -> None:
    parts = data.split(":")
    title_id = int(parts[1])
    episode_id = int(parts[2]) if len(parts) > 2 else None
    quality_options = await fetch_quality_options(session, title_id, episode_id)
    keyboard = keyboards.quality_menu_keyboard(title_id, episode_id, quality_options)
    await query.message.edit_reply_markup(reply_markup=keyboard)
    await query.answer()


async def _handle_audio_set(
    query: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
    data: str,
    tg_user_id: int,
) -> None:
    parts = data.split(":")
    title_id = int(parts[1])
    episode_id = int(parts[2]) if len(parts) > 3 else None
    audio_id = int(parts[-1])
    state = await get_user_state(session, tg_user_id)
    quality_id = None
    if state.active_variant_id:
        variant = await fetch_variant(session, state.active_variant_id)
        if variant:
            quality_id = variant.quality_id
    if quality_id is None:
        options = await fetch_quality_options(session, title_id, episode_id)
        quality_id = options[0][0] if options else None
    if quality_id is None:
        await query.answer("Нет качества для выбора.", show_alert=True)
        return
    await _handle_watch_request(
        query.bot,
        session,
        settings,
        tg_user_id,
        title_id,
        episode_id,
        audio_id,
        quality_id,
    )
    await query.answer()


async def _handle_quality_set(
    query: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
    data: str,
    tg_user_id: int,
) -> None:
    parts = data.split(":")
    title_id = int(parts[1])
    episode_id = int(parts[2]) if len(parts) > 3 else None
    quality_id = int(parts[-1])
    state = await get_user_state(session, tg_user_id)
    audio_id = None
    if state.active_variant_id:
        variant = await fetch_variant(session, state.active_variant_id)
        if variant:
            audio_id = variant.audio_id
    if audio_id is None:
        options = await fetch_audio_options(session, title_id, episode_id)
        audio_id = options[0][0] if options else None
    if audio_id is None:
        await query.answer("Нет озвучки для выбора.", show_alert=True)
        return
    await _handle_watch_request(
        query.bot,
        session,
        settings,
        tg_user_id,
        title_id,
        episode_id,
        audio_id,
        quality_id,
    )
    await query.answer()


async def _handle_back_main(query: CallbackQuery, session: AsyncSession, data: str) -> None:
    parts = data.split(":")
    title_id = int(parts[1])
    episode_id = int(parts[2]) if len(parts) > 2 else None
    title = await fetch_title(session, title_id)
    episode = await fetch_episode(session, episode_id) if episode_id else None
    if not title:
        await query.answer()
        return
    if title.type == "series" and episode:
        keyboard = keyboards.series_keyboard(title_id, episode.id)
    else:
        keyboard = keyboards.movie_keyboard(title_id)
    await query.message.edit_reply_markup(reply_markup=keyboard)
    await query.answer()


async def _handle_watch_request(
    bot: Bot,
    session: AsyncSession,
    settings: Settings,
    tg_user_id: int,
    title_id: int,
    episode_id: int | None,
    audio_id: int,
    quality_id: int,
) -> None:
    response = await _post_service_json(
        settings,
        "/api/internal/bot/watch/request",
        {
            "tg_user_id": tg_user_id,
            "title_id": title_id,
            "episode_id": episode_id,
            "audio_id": audio_id,
            "quality_id": quality_id,
        },
    )
    if not response:
        await bot.send_message(chat_id=tg_user_id, text="Не удалось запросить видео.")
        return
    mode = response.get("mode", "direct")
    variant_id = response.get("variant_id")
    if not variant_id:
        await bot.send_message(chat_id=tg_user_id, text="Видео недоступно.")
        return
    if mode == "ad_gate":
        await send_watch_card(
            bot,
            session,
            tg_user_id=tg_user_id,
            title_id=title_id,
            episode_id=episode_id,
            variant_id=variant_id,
            mode=mode,
        )
        return
    await send_video_by_variant(bot, session, tg_user_id, variant_id)


async def _post_service_json(
    settings: Settings,
    path: str,
    payload: dict,
) -> dict | None:
    if not settings.api_base_url or not settings.service_token:
        logger.warning("API_BASE_URL or SERVICE_TOKEN not configured.")
        return None
    url = f"{settings.api_base_url}{path}"
    headers = {"X-Service-Token": settings.service_token}
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError:
            logger.exception("Failed to call %s", url)
            return None
