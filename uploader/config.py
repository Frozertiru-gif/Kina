from functools import lru_cache
from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    telegram_bot_token: str = Field("replace_me", alias="TELEGRAM_BOT_TOKEN")
    telegram_storage_chat_id: int = Field(-1000000000000, alias="TELEGRAM_STORAGE_CHAT_ID")
    telegram_api_base_url: str = Field("http://telegram-bot-api:8081", alias="TELEGRAM_API_BASE_URL")
    telegram_file_api_base_url: str = Field("http://telegram-bot-api:8081/file", alias="TELEGRAM_FILE_API_BASE_URL")


@lru_cache

def get_settings() -> Settings:
    return Settings()
