import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    bot_token: str
    redis_url: str
    database_url: str
    service_token: str | None
    api_base_url: str | None
    webapp_url: str | None
    storage_chat_id: int | None
    log_level: str


def _resolve_redis_url() -> str:
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        return redis_url
    host = os.getenv("REDIS_HOST", "redis")
    port = os.getenv("REDIS_PORT", "6379")
    return f"redis://{host}:{port}/0"


def _resolve_webapp_url(api_base_url: str | None) -> str | None:
    webapp_url = os.getenv("WEBAPP_URL")
    if webapp_url:
        return webapp_url
    if not api_base_url:
        return None
    if api_base_url.endswith("/api/"):
        return api_base_url[:-5]
    if api_base_url.endswith("/api"):
        return api_base_url[:-4]
    return api_base_url


def load_settings() -> Settings:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise SystemExit("BOT_TOKEN is required")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    storage_chat_id = os.getenv("STORAGE_CHAT_ID")
    return Settings(
        bot_token=token,
        redis_url=_resolve_redis_url(),
        database_url=database_url,
        service_token=os.getenv("SERVICE_TOKEN"),
        api_base_url=os.getenv("API_BASE_URL"),
        webapp_url=_resolve_webapp_url(os.getenv("API_BASE_URL")),
        storage_chat_id=int(storage_chat_id) if storage_chat_id else None,
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )
