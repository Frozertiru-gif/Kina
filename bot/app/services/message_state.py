import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy.ext.asyncio import AsyncSession

from app import keyboards
from app.db import UserStateInfo, get_user_state, set_active_message

logger = logging.getLogger("kina.bot.message_state")


async def demote_previous_message(
    bot: Bot,
    session: AsyncSession,
    tg_user_id: int,
) -> UserStateInfo:
    state = await get_user_state(session, tg_user_id)
    if not state.active_message_id or not state.active_chat_id:
        return state
    if not state.active_title_id:
        return state
    keyboard = keyboards.reopen_hide_keyboard(
        state.active_title_id,
        state.active_episode_id,
    )
    try:
        await bot.edit_message_reply_markup(
            chat_id=state.active_chat_id,
            message_id=state.active_message_id,
            reply_markup=keyboard,
        )
    except TelegramBadRequest as exc:
        logger.info("Failed to demote message: %s", exc)
    return state


async def mark_active_message(
    session: AsyncSession,
    tg_user_id: int,
    chat_id: int,
    message_id: int,
    title_id: int | None,
    episode_id: int | None,
    variant_id: int | None,
) -> None:
    await set_active_message(
        session,
        tg_user_id=tg_user_id,
        chat_id=chat_id,
        message_id=message_id,
        title_id=title_id,
        episode_id=episode_id,
        variant_id=variant_id,
    )
