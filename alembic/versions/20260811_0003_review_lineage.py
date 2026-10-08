"""Add review audit and field lineage.

Revision ID: 20260811_0003
Revises: 20260811_0002
"""
from alembic import op
from app.db.base import Base
import app.db.models  # noqa: F401
revision="20260811_0003"
down_revision="20260811_0002"
branch_labels=None
depends_on=None
def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), tables=[table for table in Base.metadata.tables.values() if table.schema == "governance"])
def downgrade() -> None:
    for name in ("field_lineage","mapping_review"):
        op.drop_table(name, schema="governance")
