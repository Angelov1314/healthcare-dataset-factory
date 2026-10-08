"""Add immutable mapping proposals and resolutions.

Revision ID: 20260811_0004
Revises: 20260811_0003
"""
from alembic import op
from app.db.base import Base
import app.db.models  # noqa: F401
revision="20260811_0004"
down_revision="20260811_0003"
branch_labels=None
depends_on=None
def upgrade() -> None: Base.metadata.create_all(bind=op.get_bind(), tables=[table for table in Base.metadata.tables.values() if table.schema == "governance"])
def downgrade() -> None:
    op.drop_table("proposal_resolution",schema="governance")
    op.drop_table("mapping_proposal",schema="governance")
