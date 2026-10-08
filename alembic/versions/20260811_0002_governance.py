"""Add canonical and governance storage.

Revision ID: 20260811_0002
Revises: 20260811_0001
"""
from alembic import op
from app.db.base import Base
import app.db.models  # noqa: F401

revision = "20260811_0002"
down_revision = "20260811_0001"
branch_labels = None
depends_on = None

def upgrade() -> None:
    for schema in ("canonical", "governance"):
        op.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
    Base.metadata.create_all(bind=op.get_bind(), tables=[table for table in Base.metadata.tables.values() if table.schema in {"canonical", "governance"}])

def downgrade() -> None:
    for schema in ("governance", "canonical"):
        op.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
