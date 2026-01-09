import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.handlers import build_router
from app.redis import get_redis
from app.settings import load_settings
from app.db import create_session_maker
from app.workers.queue_worker import run_queue_worker


def configure_logging(level: str) -> None:
    logging.basicConfig(level=level)


async def main() -> None:
    settings = load_settings()
    configure_logging(settings.log_level)
    bot = Bot(token=settings.bot_token)
    dispatcher = Dispatcher()

    session_maker = create_session_maker(settings.database_url)
    redis = get_redis(settings.redis_url)

    dispatcher.include_router(build_router(settings, session_maker))
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
