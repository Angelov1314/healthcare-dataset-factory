"""Add OMOP-lite and cohort run storage.

Revision ID: 20260811_0006
Revises: 20260811_0005
"""
from alembic import op
from app.db.base import Base
import app.db.models  # noqa: F401
revision="20260811_0006"; down_revision="20260811_0005"; branch_labels=None; depends_on=None
def upgrade() -> None:
    op.execute('CREATE SCHEMA IF NOT EXISTS "omop"')
    op.execute('CREATE SCHEMA IF NOT EXISTS "cohort"')
    op.execute('ALTER TABLE canonical.measurement ADD COLUMN IF NOT EXISTS source_visit_id TEXT')
    op.execute('ALTER TABLE canonical.measurement ADD COLUMN IF NOT EXISTS measured_at VARCHAR(10)')
    Base.metadata.create_all(bind=op.get_bind(), tables=[table for table in Base.metadata.tables.values() if table.schema in {"omop", "cohort"}])
def downgrade() -> None:
    op.execute('DROP SCHEMA IF EXISTS "cohort" CASCADE'); op.execute('DROP SCHEMA IF EXISTS "omop" CASCADE')
