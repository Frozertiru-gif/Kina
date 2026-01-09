"""audit events

Revision ID: 0002_audit_events
Revises: 0001_initial
Create Date: 2025-01-01 00:00:10.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0002_audit_events"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("actor_type", sa.String(length=20), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("actor_admin_id", sa.Integer(), sa.ForeignKey("admins.id")),
        sa.Column("action", sa.String(length=255), nullable=False),
        sa.Column("entity_type", sa.String(length=255), nullable=False),
        sa.Column("entity_id", sa.Integer()),
        sa.Column("metadata_json", postgresql.JSONB()),
    )


def downgrade() -> None:
    op.drop_table("audit_events")
