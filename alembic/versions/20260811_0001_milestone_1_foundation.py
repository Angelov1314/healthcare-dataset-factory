"""Create Milestone 1 source and raw storage zones.

Revision ID: 20260811_0001
Revises:
Create Date: 2026-08-11 00:00:00
"""

from alembic import op

from app.db.base import Base
import app.db.models  # noqa: F401 - registers tables

revision = "20260811_0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMAS = ("his_src", "emr_src", "lis_src", "raw")


def upgrade() -> None:
    """Create isolated source and raw schemas plus registered ORM tables."""

    for schema in SCHEMAS:
        op.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
    Base.metadata.create_all(bind=op.get_bind(), tables=[table for table in Base.metadata.tables.values() if table.schema in SCHEMAS])


def downgrade() -> None:
    """Remove only tables and schemas introduced by this migration."""

    Base.metadata.drop_all(bind=op.get_bind(), tables=[table for table in Base.metadata.tables.values() if table.schema in SCHEMAS])
    for schema in reversed(SCHEMAS):
        op.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
