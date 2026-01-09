from aiogram import Bot, Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot.keyboards import default_keyboard
from bot.utils.active_message import set_active_message

router = Router()


@router.message(CommandStart())
async def start_handler(message: Message, bot: Bot) -> None:
    sent = await message.answer("Welcome to Kina!", reply_markup=default_keyboard())
    await set_active_message(bot, sent)
