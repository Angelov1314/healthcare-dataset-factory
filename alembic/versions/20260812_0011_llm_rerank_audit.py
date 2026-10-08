"""Add safe optional LLM rerank audit records.

Revision ID: 20260812_0011
Revises: 20260812_0010
"""
from alembic import op
from app.db.base import Base
import app.db.models  # noqa: F401

revision = "20260812_0011"
down_revision = "20260812_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.tables["mapping.mapping_rerank_attempt"].create(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.tables["mapping.mapping_rerank_attempt"].drop(bind=op.get_bind())
