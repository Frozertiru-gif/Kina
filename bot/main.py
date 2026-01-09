import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import get_settings
from bot.handlers import actions, start
from bot.redis_store import close_redis


async def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        base_url=settings.telegram_api_base_url,
        file_url=settings.telegram_file_api_base_url,
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(start.router)
    dispatcher.include_router(actions.router)

    try:
        await dispatcher.start_polling(bot)
    finally:
        await close_redis()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
