from aiogram import Bot, Router
from aiogram.types import CallbackQuery

from bot.keyboards import default_keyboard
from bot.utils.active_message import set_active_message

router = Router()


@router.callback_query(lambda c: c.data == "return")
async def return_handler(query: CallbackQuery, bot: Bot) -> None:
    await query.answer()
    sent = await query.message.answer("Back to main menu.", reply_markup=default_keyboard())
    await set_active_message(bot, sent)
