import asyncio
import logging
import os

from aiogram import Bot


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    token = os.getenv("BOT_TOKEN", "")
    if not token:
        logging.warning("BOT_TOKEN is not set; running in placeholder mode")
    Bot(token=token or "placeholder-token")
    logging.info("started")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
