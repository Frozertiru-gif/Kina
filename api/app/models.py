from sqlalchemy import BigInteger, Column, DateTime, Integer, String
from sqlalchemy.sql import func

from app.db import Base


class UserState(Base):
    __tablename__ = "user_states"

    user_id = Column(BigInteger, primary_key=True)
    active_message_id = Column(Integer, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class StoredVideo(Base):
    __tablename__ = "stored_videos"

    id = Column(Integer, primary_key=True, index=True)
    telegram_file_id = Column(String, nullable=False)
    storage_message_id = Column(BigInteger, nullable=False)
    storage_chat_id = Column(BigInteger, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
