import asyncio
import json
import logging

from aiogram import Bot
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import keyboards
from app.services.media_sender import send_video_by_variant, send_watch_card
from app.settings import Settings

logger = logging.getLogger("kina.bot.queue_worker")


WATCH_CARD_QUEUE = "send_watch_card_queue"
VIDEO_QUEUE = "send_video_queue"
VIDEO_VIP_QUEUE = "send_video_vip_queue"
NOTIFY_QUEUE = "notify_queue"


async def run_queue_worker(
    bot: Bot,
    settings: Settings,
    session_maker: async_sessionmaker[AsyncSession],
    redis: Redis,
) -> None:
    queues = [VIDEO_VIP_QUEUE, VIDEO_QUEUE, WATCH_CARD_QUEUE, NOTIFY_QUEUE]
    while True:
        try:
            result = await redis.brpop(queues, timeout=5)
        except asyncio.CancelledError:
            break
        except RedisError:
            logger.exception("Queue worker redis error")
            redis.connection_pool.disconnect()
            await asyncio.sleep(1)
            continue
        except Exception:  # noqa: BLE001
            logger.exception("Queue worker error")
            await asyncio.sleep(1)
            continue
        if not result:
            continue
        queue_name, raw_payload = result
        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError:
            logger.warning("Invalid payload in %s: %s", queue_name, raw_payload)
            continue
        async with session_maker() as session:
            await _dispatch_job(bot, session, queue_name, payload)


async def _dispatch_job(
    bot: Bot,
    session: AsyncSession,
    queue_name: str,
    payload: dict,
) -> None:
    if queue_name in {VIDEO_QUEUE, VIDEO_VIP_QUEUE}:
        await _handle_send_video(bot, session, payload)
        return
    if queue_name == WATCH_CARD_QUEUE:
        await _handle_send_watch_card(bot, session, payload)
        return
    if queue_name == NOTIFY_QUEUE:
        await _handle_notify(bot, payload)
        return
    logger.warning("Unknown queue %s", queue_name)


async def _handle_send_watch_card(
    bot: Bot,
    session: AsyncSession,
    payload: dict,
) -> None:
    await send_watch_card(
        bot,
        session,
        tg_user_id=payload["tg_user_id"],
        title_id=payload["title_id"],
        episode_id=payload.get("episode_id"),
        variant_id=payload.get("variant_id"),
        mode=payload.get("mode", ""),
    )


async def _handle_send_video(bot: Bot, session: AsyncSession, payload: dict) -> None:
    await send_video_by_variant(
        bot,
        session,
        tg_user_id=payload["tg_user_id"],
        variant_id=payload["variant_id"],
    )


async def _handle_notify(bot: Bot, payload: dict) -> None:
    tg_user_id = payload["tg_user_id"]
    text = payload.get("text") or "У вас новое уведомление."
    title_id = payload.get("title_id")
    episode_id = payload.get("episode_id")
    keyboard = None
    if title_id is not None and episode_id is not None:
        keyboard = keyboards.notification_keyboard(int(title_id), int(episode_id))
    await bot.send_message(chat_id=tg_user_id, text=text, reply_markup=keyboard)
