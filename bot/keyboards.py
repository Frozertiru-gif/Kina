from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def default_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Do Action", callback_data="action")]]
    )


def return_hide_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Return", callback_data="return")]]
    )
