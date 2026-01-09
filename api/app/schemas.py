from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


class VideoCreate(BaseModel):
    telegram_file_id: str
    storage_message_id: int
    storage_chat_id: int


class VideoResponse(VideoCreate):
    id: int

    class Config:
        orm_mode = True
