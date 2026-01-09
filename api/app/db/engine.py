from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.settings import get_settings


def _build_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(settings.database_url)


engine = _build_engine()


async def init_db() -> None:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
