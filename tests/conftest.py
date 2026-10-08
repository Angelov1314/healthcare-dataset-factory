"""PostgreSQL-backed fixtures for the supported test workflow."""

from __future__ import annotations

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import create_session_factory


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    """Apply Alembic migrations to the mandatory PostgreSQL test database."""

    if "healthcare_factory_test" not in os.environ.get("DATABASE_URL", ""):
        raise RuntimeError("Tests require DATABASE_URL pointing to healthcare_factory_test")
    get_settings.cache_clear()
    command.upgrade(Config("alembic.ini"), "head")


@pytest.fixture()
def db_session(migrated_database: None):
    """Yield an empty test-database session for one test."""

    session = create_session_factory()()
    try:
        session.execute(text("TRUNCATE mapping.import_audit_event, mapping.factory_benchmark_candidate_snapshot, mapping.factory_benchmark_profile_snapshot, mapping.factory_benchmark_run, mapping.mapping_suggestion_review, mapping.mapping_rerank_attempt, mapping.mapping_candidate, mapping.mapping_suggestion, mapping.source_field_profile, mapping.import_job, product.export_attempt, product.dataset_product, product.privacy_policy, cohort.member, cohort.run, cohort.definition, omop.mapping_rejection, omop.drug_exposure, omop.procedure_occurrence, omop.adapter_event, omop.measurement, omop.condition_occurrence, omop.visit_occurrence, omop.person, omop.mapping_run, governance.mapping_conflict_resolution, governance.proposal_resolution, governance.mapping_proposal, governance.mapping_review, governance.field_lineage, raw.ingestion_rejection, raw.record, raw.ingestion_run, raw.source_snapshot CASCADE"))
        session.commit()
        yield session
    finally:
        session.close()
