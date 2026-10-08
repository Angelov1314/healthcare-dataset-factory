"""Add persisted local hybrid retrieval candidates.

Revision ID: 20260812_0010
Revises: 20260812_0009
"""
from alembic import op
from app.db.base import Base
import app.db.models  # noqa: F401

revision = "20260812_0010"
down_revision = "20260812_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.tables["mapping.mapping_candidate"].create(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.tables["mapping.mapping_candidate"].drop(bind=op.get_bind())
