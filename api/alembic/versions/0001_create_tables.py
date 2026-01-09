"""create tables

Revision ID: 0001
Revises: 
Create Date: 2024-01-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_states",
        sa.Column("user_id", sa.BigInteger(), primary_key=True),
        sa.Column("active_message_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "stored_videos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_file_id", sa.String(), nullable=False),
        sa.Column("storage_message_id", sa.BigInteger(), nullable=False),
        sa.Column("storage_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_stored_videos_id", "stored_videos", ["id"])


def downgrade() -> None:
    op.drop_index("ix_stored_videos_id", table_name="stored_videos")
    op.drop_table("stored_videos")
    op.drop_table("user_states")
