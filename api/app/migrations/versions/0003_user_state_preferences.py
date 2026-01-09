"""add user state preferences

Revision ID: 0003_user_state_preferences
Revises: 0002_audit_events
Create Date: 2025-02-20 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0003_user_state_preferences"
down_revision = "0002_audit_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_state", sa.Column("preferred_audio_id", sa.Integer(), nullable=True))
    op.add_column("user_state", sa.Column("preferred_quality_id", sa.Integer(), nullable=True))
    op.add_column("user_state", sa.Column("last_title_id", sa.Integer(), nullable=True))
    op.add_column("user_state", sa.Column("last_episode_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_state", "last_episode_id")
    op.drop_column("user_state", "last_title_id")
    op.drop_column("user_state", "preferred_quality_id")
    op.drop_column("user_state", "preferred_audio_id")
