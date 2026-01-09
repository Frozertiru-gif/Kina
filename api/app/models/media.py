from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AudioTrack(Base):
    __tablename__ = "audio_tracks"

    id: Mapped[int] = mapped_column(primary_key=True)
    language: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))


class Quality(Base):
    __tablename__ = "qualities"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(50), nullable=False)
    resolution: Mapped[str | None] = mapped_column(String(50))


class MediaVariant(Base):
    __tablename__ = "media_variants"
    __table_args__ = (
        Index(
            "uq_media_variants_movie",
            "title_id",
            "audio_id",
            "quality_id",
            unique=True,
            postgresql_where=text("episode_id IS NULL"),
        ),
        Index(
            "uq_media_variants_episode",
            "episode_id",
            "audio_id",
            "quality_id",
            unique=True,
            postgresql_where=text("episode_id IS NOT NULL"),
        ),
        Index("ix_media_variants_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title_id: Mapped[int] = mapped_column(ForeignKey("titles.id"), nullable=False)
    episode_id: Mapped[int | None] = mapped_column(ForeignKey("episodes.id"))
    audio_id: Mapped[int] = mapped_column(ForeignKey("audio_tracks.id"), nullable=False)
    quality_id: Mapped[int] = mapped_column(ForeignKey("qualities.id"), nullable=False)
    telegram_file_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    audio: Mapped[AudioTrack] = relationship()
    quality: Mapped[Quality] = relationship()


class UploadJob(Base):
    __tablename__ = "upload_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    media_variant_id: Mapped[int] = mapped_column(
        ForeignKey("media_variants.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    media_variant: Mapped[MediaVariant] = relationship()
