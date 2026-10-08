"""Split raw EMR OMOP adapters into explicit drug and procedure domains.

Revision ID: 20260811_0007
Revises: 20260811_0006
"""
from alembic import op
from app.db.base import Base
import app.db.models  # noqa: F401

revision = "20260811_0007"
down_revision = "20260811_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), tables=[
        Base.metadata.tables["omop.drug_exposure"], Base.metadata.tables["omop.procedure_occurrence"],
    ])


def downgrade() -> None:
    op.drop_table("procedure_occurrence", schema="omop")
    op.drop_table("drug_exposure", schema="omop")
