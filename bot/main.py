import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import MenuButtonWebApp, WebAppInfo

from app.handlers import build_router
from app.redis import get_redis
from app.settings import load_settings
from app.logging_utils import configure_logging
from app.db import create_session_maker
from app.workers.queue_worker import run_queue_worker

logger = logging.getLogger("kina.bot.main")


async def main() -> None:
    settings = load_settings()
    configure_logging(settings.log_level)
    bot = Bot(token=settings.bot_token)
    dispatcher = Dispatcher()

    session_maker = create_session_maker(settings.database_url)
    redis = get_redis(settings.redis_url)

    dispatcher.include_router(build_router(settings, session_maker, redis))
    try:
        await _set_menu_button(bot, settings.webapp_url)
    except NameError:
        logger.warning("Menu button helper is not defined; skipping", exc_info=True)
    worker_task = asyncio.create_task(
        run_queue_worker(bot, settings, session_maker, redis),
        name="queue-worker",
    )

    try:
        await dispatcher.start_polling(bot)
    finally:
        worker_task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())


async def _set_menu_button(bot: Bot, webapp_url: str) -> None:
    try:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="Каталог", web_app=WebAppInfo(url=webapp_url)),
        )
    except Exception:
        logger.warning("Failed to set chat menu button", exc_info=True)
