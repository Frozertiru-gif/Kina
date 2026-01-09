from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message

from bot.db import get_active_message_id, set_active_message_id
from bot.keyboards import return_hide_keyboard


async def set_active_message(bot: Bot, message: Message) -> None:
    user_id = message.chat.id
    previous_message_id = await get_active_message_id(user_id)
    if previous_message_id:
        try:
            await bot.edit_message_reply_markup(
                chat_id=user_id,
                message_id=previous_message_id,
                reply_markup=return_hide_keyboard(),
            )
        except TelegramBadRequest:
            pass

    await set_active_message_id(user_id, message.message_id)
