"""Milestone 3 deterministic healthcare-semantics integration tests."""
from sqlalchemy import func, select

from app.canonical.service import canonicalize
from app.cohort.service import create_definition, preview_cohort, run_cohort, seed_liver_definition
from app.db.models import CohortMember, OmopDrugExposure, OmopMeasurement, OmopPerson, OmopProcedureOccurrence
from app.governance.service import seed_mapping_set
from app.ingestion.service import persist_snapshot, run_ingestion
from app.omop.service import manifest_hash, run_omop_mapping
from app.product.service import build_dataset_product
from app.governance.service import run_quality
from app.synthetic.generator import generate_snapshot


def _canonical_run(db_session):
    persist_snapshot(db_session, generate_snapshot(31, 12))
    ingestion = run_ingestion(db_session)
    mapping = seed_mapping_set(db_session)
    return canonicalize(db_session, ingestion["ingestion_run_id"], mapping.mapping_set_id)


def test_omop_mapping_is_deterministic_and_persists_manifest(db_session) -> None:
    """The same input and catalog resolves to the same completed mapping run."""
    canonical = _canonical_run(db_session)
    mapped = run_omop_mapping(db_session, canonical["id"])
    again = run_omop_mapping(db_session, canonical["id"])
    assert mapped["id"] == again["id"]
    assert mapped["manifest_hash"] == manifest_hash()
    assert db_session.scalar(select(func.count()).select_from(OmopPerson)) == 10
    assert db_session.scalar(select(func.count()).select_from(OmopMeasurement)) == 34
    assert db_session.scalar(select(func.count()).select_from(OmopDrugExposure)) == 11
    assert db_session.scalar(select(func.count()).select_from(OmopProcedureOccurrence)) == 11


def test_seeded_liver_cohort_is_versioned_and_privacy_safe(db_session) -> None:
    """Preview and persisted membership have equal count without source IDs."""
    canonical = _canonical_run(db_session)
    omop = run_omop_mapping(db_session, canonical["id"])
    definition = seed_liver_definition(db_session)
    preview = preview_cohort(db_session, definition.cohort_definition_id, omop["id"])
    result = run_cohort(db_session, definition.cohort_definition_id, omop["id"])
    assert preview
    assert result["member_count"] == len(preview)
    assert db_session.scalar(select(func.count()).select_from(CohortMember)) == len(preview)
    assert "patient" not in result


def test_definition_rejects_unsupported_window_and_duplicate_version(db_session) -> None:
    """Definitions are append-only and v1 rejects unsupported time semantics."""
    definition = seed_liver_definition(db_session)
    try:
        create_definition(db_session, "liver-cohort", "1.0.0", definition.condition_tree, "tester")
        assert False, "expected duplicate version"
    except RuntimeError:
        pass
    try:
        create_definition(db_session, "alternate", "1.0.0", definition.condition_tree, "tester", "30_days")
        assert False, "expected unsupported window"
    except ValueError:
        pass


def test_product_export_is_pseudonymized_and_idempotent(db_session) -> None:
    """The product artifact retains selected dates but excludes raw identifiers."""
    canonical = _canonical_run(db_session)
    quality = run_quality(db_session, canonical["id"])
    omop = run_omop_mapping(db_session, canonical["id"])
    cohort = run_cohort(db_session, seed_liver_definition(db_session).cohort_definition_id, omop["id"])
    result = build_dataset_product(db_session, cohort["id"], quality["id"], "test-secret", "test-key")
    repeated = build_dataset_product(db_session, cohort["id"], quality["id"], "test-secret", "test-key")
    assert result["id"] == repeated["id"]
    csv_text = open(result["csv_path"], encoding="utf-8").read()
    assert "pseudonymous_patient_id" in csv_text
    assert "source_patient_id" not in csv_text and "date_of_birth" not in csv_text and "city" not in csv_text
