"""Add metadata-only AI mapping import foundation.

Revision ID: 20260812_0009
Revises: 20260811_0008
"""
from alembic import op
from app.db.base import Base
import app.db.models  # noqa: F401

revision = "20260812_0009"
down_revision = "20260811_0008"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute('CREATE SCHEMA IF NOT EXISTS "mapping"')
    Base.metadata.create_all(bind=op.get_bind(), tables=[table for table in Base.metadata.tables.values() if table.schema == "mapping"])

def downgrade() -> None:
    op.execute('DROP SCHEMA IF EXISTS "mapping" CASCADE')
