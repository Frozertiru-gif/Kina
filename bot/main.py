import asyncio
import logging
import os

from aiogram import Bot, Dispatcher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kina.bot")


def get_bot_token() -> str:
    token = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("BOT_TOKEN is required")
    return token


async def main() -> None:
    bot = Bot(token=get_bot_token())
    dispatcher = Dispatcher()
    logger.info("started")

    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
