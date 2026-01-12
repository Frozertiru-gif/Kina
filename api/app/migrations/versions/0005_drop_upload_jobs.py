"""drop legacy upload_jobs table

Revision ID: 0005_drop_upload_jobs
Revises: 0004_admins_auth_fields
Create Date: 2025-02-27 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0005_drop_upload_jobs"
down_revision = "0004_admins_auth_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if inspector.has_table("upload_jobs", schema="public"):
        op.execute(sa.text("ALTER TABLE public.upload_jobs DROP CONSTRAINT IF EXISTS upload_jobs_variant_id_fkey"))
        op.drop_table("upload_jobs", schema="public")


def downgrade() -> None:
    pass
