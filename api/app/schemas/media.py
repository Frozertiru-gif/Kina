from datetime import datetime

from pydantic import BaseModel


class AudioTrackRead(BaseModel):
    id: int
    language: str
    name: str | None = None

    class Config:
        from_attributes = True


class QualityRead(BaseModel):
    id: int
    label: str
    resolution: str | None = None

    class Config:
        from_attributes = True


class MediaVariantRead(BaseModel):
    id: int
    title_id: int
    episode_id: int | None = None
    audio_id: int
    quality_id: int
    telegram_file_id: str | None = None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
