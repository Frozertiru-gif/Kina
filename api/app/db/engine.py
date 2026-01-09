from sqlalchemy.ext.asyncio import create_async_engine

from app.settings import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
)
