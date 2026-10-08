"""Add immutable factory benchmark snapshots.

Revision ID: 20260813_0013
Revises: 20260812_0012
"""
from alembic import op
from app.db.base import Base
import app.db.models  # noqa: F401

revision = "20260813_0013"
down_revision = "20260812_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in (
        "mapping.factory_benchmark_run",
        "mapping.factory_benchmark_profile_snapshot",
        "mapping.factory_benchmark_candidate_snapshot",
    ):
        Base.metadata.tables[table].create(bind=op.get_bind())


def downgrade() -> None:
    for table in (
        "mapping.factory_benchmark_candidate_snapshot",
        "mapping.factory_benchmark_profile_snapshot",
        "mapping.factory_benchmark_run",
    ):
        Base.metadata.tables[table].drop(bind=op.get_bind())
