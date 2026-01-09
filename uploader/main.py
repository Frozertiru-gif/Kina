import argparse
import asyncio
import json
from pathlib import Path

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import FSInputFile
from tenacity import retry, stop_after_attempt, wait_exponential

from uploader.config import get_settings


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, max=4))
async def upload_video(bot: Bot, chat_id: int, file_path: Path) -> dict:
    message = await bot.send_video(chat_id=chat_id, video=FSInputFile(file_path))
    return {
        "telegram_file_id": message.video.file_id,
        "storage_message_id": message.message_id,
        "storage_chat_id": chat_id,
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Upload a local video to storage chat")
    parser.add_argument("file", type=Path, help="Path to video file")
    args = parser.parse_args()

    settings = get_settings()
    session = AiohttpSession(timeout=30)
    bot = Bot(
        token=settings.telegram_bot_token,
        session=session,
        base_url=settings.telegram_api_base_url,
        file_url=settings.telegram_file_api_base_url,
    )

    try:
        payload = await upload_video(bot, settings.telegram_storage_chat_id, args.file)
        print(json.dumps(payload))
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
