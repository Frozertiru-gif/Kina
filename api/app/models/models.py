import enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TitleType(enum.Enum):
    MOVIE = "movie"
    SERIES = "series"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str | None] = mapped_column(String(255))
    language_code: Mapped[str | None] = mapped_column(String(10))
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    is_banned: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    ban_reason: Mapped[str | None] = mapped_column(Text)


class UserState(Base):
    __tablename__ = "user_state"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    active_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    active_message_id: Mapped[int | None] = mapped_column(BigInteger)
    active_variant_id: Mapped[int | None] = mapped_column(Integer)
    active_title_id: Mapped[int | None] = mapped_column(Integer)
    active_episode_id: Mapped[int | None] = mapped_column(Integer)
    preferred_audio_id: Mapped[int | None] = mapped_column(Integer)
    preferred_quality_id: Mapped[int | None] = mapped_column(Integer)
    last_title_id: Mapped[int | None] = mapped_column(Integer)
    last_episode_id: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Title(Base):
    __tablename__ = "titles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[TitleType] = mapped_column(
        Enum(
            TitleType,
            name="title_type",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    original_name: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    year: Mapped[int | None] = mapped_column(Integer)
    poster_url: Mapped[str | None] = mapped_column(String(512))
    is_published: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Season(Base):
    __tablename__ = "seasons"
    __table_args__ = (
        UniqueConstraint("title_id", "season_number", name="uq_seasons_title_season"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title_id: Mapped[int] = mapped_column(ForeignKey("titles.id", ondelete="CASCADE"))
    season_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Episode(Base):
    __tablename__ = "episodes"
    __table_args__ = (
        UniqueConstraint("season_id", "episode_number", name="uq_episodes_season_episode"),
        Index("ix_episodes_published_at", "published_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title_id: Mapped[int] = mapped_column(ForeignKey("titles.id", ondelete="CASCADE"))
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"))
    episode_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    air_date: Mapped[Date | None] = mapped_column(Date)
    published_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AudioTrack(Base):
    __tablename__ = "audio_tracks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)


class Quality(Base):
    __tablename__ = "qualities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)


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

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title_id: Mapped[int] = mapped_column(ForeignKey("titles.id", ondelete="CASCADE"))
    episode_id: Mapped[int | None] = mapped_column(ForeignKey("episodes.id"))
    audio_id: Mapped[int] = mapped_column(ForeignKey("audio_tracks.id"))
    quality_id: Mapped[int] = mapped_column(ForeignKey("qualities.id"))
    telegram_file_id: Mapped[str | None] = mapped_column(String(255))
    storage_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    storage_message_id: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    duration_sec: Mapped[int | None] = mapped_column(Integer)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class UploadJob(Base):
    __tablename__ = "upload_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_by_admin_id: Mapped[int | None] = mapped_column(ForeignKey("admins.id"))
    local_path: Mapped[str] = mapped_column(String(512), nullable=False)
    variant_id: Mapped[int] = mapped_column(ForeignKey("media_variants.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Favorite(Base):
    __tablename__ = "favorites"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    title_id: Mapped[int] = mapped_column(
        ForeignKey("titles.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Subscription(Base):
    __tablename__ = "subscriptions"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    title_id: Mapped[int] = mapped_column(
        ForeignKey("titles.id", ondelete="CASCADE"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ViewEvent(Base):
    __tablename__ = "view_events"
    __table_args__ = (
        Index("ix_view_events_created_at", "created_at"),
        Index("ix_view_events_title_created", "title_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title_id: Mapped[int] = mapped_column(ForeignKey("titles.id", ondelete="CASCADE"))
    episode_id: Mapped[int | None] = mapped_column(ForeignKey("episodes.id"))
    variant_id: Mapped[int] = mapped_column(ForeignKey("media_variants.id"))
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    source: Mapped[str] = mapped_column(String(100), nullable=False)


class PremiumPlan(Base):
    __tablename__ = "premium_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    months: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[float | None] = mapped_column(Numeric(10, 2))
    currency: Mapped[str | None] = mapped_column(String(10))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)


class UserPremium(Base):
    __tablename__ = "user_premium"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    premium_until: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_payment_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    plan_id: Mapped[int] = mapped_column(ForeignKey("premium_plans.id"), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    paid_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))


class ReferralCode(Base):
    __tablename__ = "referral_codes"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Referral(Base):
    __tablename__ = "referrals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    referrer_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    referred_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ReferralReward(Base):
    __tablename__ = "referral_rewards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    referrer_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    referred_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    reward_days: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    applied: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    applied_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))


class Admin(Base):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    actor_admin_id: Mapped[int | None] = mapped_column(ForeignKey("admins.id"))
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(Integer)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)
