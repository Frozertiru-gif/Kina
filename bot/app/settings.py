import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    bot_token: str
    redis_url: str
    database_url: str
    service_token: str | None
    admin_token: str | None
    api_base_url: str | None
    webapp_url: str
    storage_chat_id: int | None
    ingest_chat_id: int | None
    log_level: str


def _resolve_redis_url() -> str:
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        return redis_url
    host = os.getenv("REDIS_HOST", "redis")
    port = os.getenv("REDIS_PORT", "6379")
    return f"redis://{host}:{port}/0"


def load_settings() -> Settings:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise SystemExit("BOT_TOKEN is required")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    public_base_url = os.getenv("PUBLIC_BASE_URL")
    if public_base_url:
        webapp_url = f"{public_base_url.rstrip('/')}/"
    else:
        webapp_url = os.getenv("WEBAPP_URL")
        if not webapp_url:
            raise SystemExit("WEBAPP_URL is required when PUBLIC_BASE_URL is not set")
    storage_chat_id = os.getenv("STORAGE_CHAT_ID")
    ingest_chat_id = os.getenv("INGEST_CHAT_ID")
    return Settings(
        bot_token=token,
        redis_url=_resolve_redis_url(),
        database_url=database_url,
        service_token=os.getenv("SERVICE_TOKEN"),
        admin_token=(
            os.getenv("ADMIN_TOKEN")
            or os.getenv("ADMIN_SERVICE_TOKEN")
            or os.getenv("SERVICE_TOKEN")
        ),
        api_base_url=os.getenv("API_BASE_URL", "http://api:8000"),
        webapp_url=webapp_url,
        storage_chat_id=int(storage_chat_id) if storage_chat_id else None,
        ingest_chat_id=int(ingest_chat_id) if ingest_chat_id else None,
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )
