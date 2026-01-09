from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import StoredVideo
from app.schemas import VideoCreate, VideoResponse

router = APIRouter(prefix="/videos")


@router.post("", response_model=VideoResponse)
async def create_video(payload: VideoCreate, session: AsyncSession = Depends(get_session)) -> VideoResponse:
    video = StoredVideo(
        telegram_file_id=payload.telegram_file_id,
        storage_message_id=payload.storage_message_id,
        storage_chat_id=payload.storage_chat_id,
    )
    session.add(video)
    await session.commit()
    await session.refresh(video)
    return VideoResponse.from_orm(video)
