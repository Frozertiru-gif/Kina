"""admin auth fields

Revision ID: 0004_admins_auth_fields
Revises: 0003_user_state_preferences
Create Date: 2025-02-20 00:00:10.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0004_admins_auth_fields"
down_revision = "0003_user_state_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("admins", sa.Column("username", sa.String(length=255), nullable=True))
    op.add_column("admins", sa.Column("password_hash", sa.String(length=255), nullable=True))
    op.execute(sa.text("UPDATE admins SET username = CAST(tg_user_id AS TEXT) WHERE username IS NULL"))
    op.execute(sa.text("UPDATE admins SET password_hash = 'migrated' WHERE password_hash IS NULL"))
    op.alter_column("admins", "username", nullable=False)
    op.alter_column("admins", "password_hash", nullable=False)
    op.create_unique_constraint("uq_admins_username", "admins", ["username"])
    op.drop_column("admins", "role")
    op.drop_column("admins", "tg_user_id")


def downgrade() -> None:
    op.add_column("admins", sa.Column("tg_user_id", sa.BigInteger(), nullable=True))
    op.add_column(
        "admins",
        sa.Column("role", sa.String(length=50), nullable=True, server_default="owner"),
    )
    op.execute(sa.text("UPDATE admins SET tg_user_id = 0 WHERE tg_user_id IS NULL"))
    op.alter_column("admins", "tg_user_id", nullable=False)
    op.drop_constraint("uq_admins_username", "admins", type_="unique")
    op.drop_column("admins", "password_hash")
    op.drop_column("admins", "username")
    op.alter_column("admins", "role", nullable=False)
    op.create_unique_constraint("uq_admins_tg_user_id", "admins", ["tg_user_id"])
