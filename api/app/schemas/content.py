from datetime import datetime

from pydantic import BaseModel


class TitleBase(BaseModel):
    type: str
    name: str
    description: str | None = None


class TitleRead(TitleBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class SeasonBase(BaseModel):
    title_id: int
    season_number: int


class SeasonRead(SeasonBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class EpisodeBase(BaseModel):
    season_id: int
    episode_number: int
    name: str | None = None
    published_at: datetime | None = None


class EpisodeRead(EpisodeBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
