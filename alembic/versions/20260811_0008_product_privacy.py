"""Add isolated privacy policy and dataset product storage.

Revision ID: 20260811_0008
Revises: 20260811_0007
"""
from alembic import op
from app.db.base import Base
import app.db.models  # noqa: F401

revision = "20260811_0008"
down_revision = "20260811_0007"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute('CREATE SCHEMA IF NOT EXISTS "product"')
    Base.metadata.create_all(bind=op.get_bind(), tables=[table for table in Base.metadata.tables.values() if table.schema == "product"])

def downgrade() -> None:
    op.execute('DROP SCHEMA IF EXISTS "product" CASCADE')
