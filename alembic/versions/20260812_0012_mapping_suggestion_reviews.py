"""Add append-only human reviews for imported mapping suggestions.

Revision ID: 20260812_0012
Revises: 20260812_0011
"""
from alembic import op
from app.db.base import Base
import app.db.models  # noqa: F401

revision = "20260812_0012"
down_revision = "20260812_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.tables["mapping.mapping_suggestion_review"].create(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.tables["mapping.mapping_suggestion_review"].drop(bind=op.get_bind())
