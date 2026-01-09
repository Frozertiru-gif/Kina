"""initial

Revision ID: 0001_initial
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admins",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tg_user_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "audio_tracks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
    )

    op.create_table(
        "premium_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("months", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(10, 2)),
        sa.Column("currency", sa.String(length=10)),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
    )

    op.create_table(
        "qualities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
    )

    op.create_table(
        "titles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("type", sa.Enum("movie", "series", name="title_type"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("original_name", sa.String(length=255)),
        sa.Column("description", sa.Text()),
        sa.Column("year", sa.Integer()),
        sa.Column("poster_url", sa.String(length=512)),
        sa.Column("is_published", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tg_user_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("username", sa.String(length=255)),
        sa.Column("first_name", sa.String(length=255)),
        sa.Column("language_code", sa.String(length=10)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_banned", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("ban_reason", sa.Text()),
    )

    op.create_table(
        "seasons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title_id", sa.Integer(), sa.ForeignKey("titles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("season_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("title_id", "season_number", name="uq_seasons_title_season"),
    )

    op.create_table(
        "episodes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title_id", sa.Integer(), sa.ForeignKey("titles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("season_id", sa.Integer(), sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("episode_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("air_date", sa.Date()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("season_id", "episode_number", name="uq_episodes_season_episode"),
    )

    op.create_index("ix_episodes_published_at", "episodes", ["published_at"])

    op.create_table(
        "media_variants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title_id", sa.Integer(), sa.ForeignKey("titles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("episode_id", sa.Integer(), sa.ForeignKey("episodes.id")),
        sa.Column("audio_id", sa.Integer(), sa.ForeignKey("audio_tracks.id"), nullable=False),
        sa.Column("quality_id", sa.Integer(), sa.ForeignKey("qualities.id"), nullable=False),
        sa.Column("telegram_file_id", sa.String(length=255)),
        sa.Column("storage_chat_id", sa.BigInteger()),
        sa.Column("storage_message_id", sa.BigInteger()),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("duration_sec", sa.Integer()),
        sa.Column("size_bytes", sa.BigInteger()),
        sa.Column("checksum_sha256", sa.String(length=64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_index("ix_media_variants_status", "media_variants", ["status"])
    op.create_index(
        "uq_media_variants_movie",
        "media_variants",
        ["title_id", "audio_id", "quality_id"],
        unique=True,
        postgresql_where=sa.text("episode_id IS NULL"),
    )
    op.create_index(
        "uq_media_variants_episode",
        "media_variants",
        ["episode_id", "audio_id", "quality_id"],
        unique=True,
        postgresql_where=sa.text("episode_id IS NOT NULL"),
    )

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("provider_payment_id", sa.String(length=255), nullable=False, unique=True),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("premium_plans.id"), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "referral_codes",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("code", sa.String(length=50), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "referrals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("referrer_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "referred_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "referral_rewards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("referrer_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("referred_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reward_days", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("applied", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "upload_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_by_admin_id", sa.Integer(), sa.ForeignKey("admins.id")),
        sa.Column("local_path", sa.String(length=512), nullable=False),
        sa.Column("variant_id", sa.Integer(), sa.ForeignKey("media_variants.id"), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "user_premium",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("premium_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "user_state",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("active_chat_id", sa.BigInteger()),
        sa.Column("active_message_id", sa.BigInteger()),
        sa.Column("active_variant_id", sa.Integer()),
        sa.Column("active_title_id", sa.Integer()),
        sa.Column("active_episode_id", sa.Integer()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "favorites",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("title_id", sa.Integer(), sa.ForeignKey("titles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "subscriptions",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("title_id", sa.Integer(), sa.ForeignKey("titles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "view_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title_id", sa.Integer(), sa.ForeignKey("titles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("episode_id", sa.Integer(), sa.ForeignKey("episodes.id")),
        sa.Column("variant_id", sa.Integer(), sa.ForeignKey("media_variants.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
    )

    op.create_index("ix_view_events_created_at", "view_events", ["created_at"])
    op.create_index("ix_view_events_title_created", "view_events", ["title_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_view_events_title_created", table_name="view_events")
    op.drop_index("ix_view_events_created_at", table_name="view_events")
    op.drop_table("view_events")
    op.drop_table("subscriptions")
    op.drop_table("favorites")
    op.drop_table("user_state")
    op.drop_table("user_premium")
    op.drop_table("upload_jobs")
    op.drop_table("referral_rewards")
    op.drop_table("referrals")
    op.drop_table("referral_codes")
    op.drop_table("payments")
    op.drop_index("uq_media_variants_episode", table_name="media_variants")
    op.drop_index("uq_media_variants_movie", table_name="media_variants")
    op.drop_index("ix_media_variants_status", table_name="media_variants")
    op.drop_table("media_variants")
    op.drop_index("ix_episodes_published_at", table_name="episodes")
    op.drop_table("episodes")
    op.drop_table("seasons")
    op.drop_table("users")
    op.drop_table("titles")
    op.drop_table("qualities")
    op.drop_table("premium_plans")
    op.drop_table("audio_tracks")
    op.drop_table("admins")
    op.execute(sa.text("DROP TYPE title_type"))
