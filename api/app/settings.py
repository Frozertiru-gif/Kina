from dataclasses import dataclass
import os


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


@dataclass(frozen=True)
class Settings:
    database_url: str = _require_env("DATABASE_URL")


settings = Settings()
