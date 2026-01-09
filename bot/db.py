from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.config import get_settings

settings = get_settings()
engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_active_message_id(user_id: int) -> int | None:
    async with SessionLocal() as session:
        result = await session.execute(
            "SELECT active_message_id FROM user_states WHERE user_id = :user_id",
            {"user_id": user_id},
        )
        row = result.fetchone()
        return row[0] if row else None


async def set_active_message_id(user_id: int, message_id: int | None) -> None:
    async with SessionLocal() as session:
        await session.execute(
            """
            INSERT INTO user_states (user_id, active_message_id)
            VALUES (:user_id, :active_message_id)
            ON CONFLICT (user_id) DO UPDATE
            SET active_message_id = :active_message_id, updated_at = now()
            """,
            {"user_id": user_id, "active_message_id": message_id},
        )
        await session.commit()
