from functools import lru_cache
from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    environment: str = Field("local", alias="ENVIRONMENT")
    log_level: str = Field("INFO", alias="LOG_LEVEL")

    postgres_host: str = Field("postgres", alias="POSTGRES_HOST")
    postgres_port: int = Field(5432, alias="POSTGRES_PORT")
    postgres_db: str = Field("kina", alias="POSTGRES_DB")
    postgres_user: str = Field("kina", alias="POSTGRES_USER")
    postgres_password: str = Field("change_me", alias="POSTGRES_PASSWORD")
    database_url: str = Field(
        "postgresql+asyncpg://kina:change_me@postgres:5432/kina",
        alias="DATABASE_URL",
    )

    redis_url: str = Field("redis://redis:6379/0", alias="REDIS_URL")

    telegram_bot_token: str = Field("replace_me", alias="TELEGRAM_BOT_TOKEN")
    telegram_storage_chat_id: int = Field(-1000000000000, alias="TELEGRAM_STORAGE_CHAT_ID")
    telegram_api_base_url: str = Field("http://telegram-bot-api:8081", alias="TELEGRAM_API_BASE_URL")
    telegram_file_api_base_url: str = Field(
        "http://telegram-bot-api:8081/file",
        alias="TELEGRAM_FILE_API_BASE_URL",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
