"""Milestone 2 canonicalization and quality integration tests."""
from sqlalchemy import func, select
from app.canonical.service import canonicalize
from app.db.models import CanonicalMeasurement, CanonicalPatient, CanonicalizationRun, LineageEvent, QualityResult
from app.governance.service import run_quality, seed_mapping_set
from app.db.models import MappingConflictResolution, MappingProposal, ProposalResolution
from app.ingestion.service import persist_snapshot, run_ingestion
from app.synthetic.generator import generate_snapshot

def test_canonical_quality_and_lineage_are_reproducible(db_session) -> None:
    """The governed path normalizes liver labs and persists 22 auditable rules."""
    persist_snapshot(db_session, generate_snapshot(31, 12))
    ingestion = run_ingestion(db_session)
    mapping = seed_mapping_set(db_session)
    canonical = canonicalize(db_session, ingestion_run_id=ingestion["ingestion_run_id"], mapping_set_id=mapping.mapping_set_id)
    assert canonicalize(db_session, ingestion_run_id=ingestion["ingestion_run_id"], mapping_set_id=mapping.mapping_set_id)["id"] == canonical["id"]
    assert db_session.scalar(select(func.count()).select_from(CanonicalPatient)) == 10
    assert db_session.scalar(select(func.count()).select_from(CanonicalMeasurement)) == 34
    quality = run_quality(db_session, canonical["id"])
    assert len(quality["rule_results"]) == 22
    assert quality["before"]["ingestion_rejections"] == 1
    assert quality["dimension_scores"].keys() == {"completeness", "validity", "consistency", "uniqueness", "referential_integrity", "clinical_plausibility"}
    assert db_session.scalar(select(func.count()).select_from(QualityResult)) == 22
    assert db_session.scalar(select(func.count()).select_from(LineageEvent)) == 2


def test_mapping_proposal_resolution_is_append_only(db_session) -> None:
    """A submitted prototype proposal may receive exactly one resolution event."""
    mapping = seed_mapping_set(db_session)
    from app.db.models import MappingDefinition
    definition = db_session.scalar(select(MappingDefinition).where(MappingDefinition.mapping_set_id == mapping.mapping_set_id))
    assert definition is not None
    proposal = MappingProposal(mapping_definition_id=definition.mapping_definition_id, proposer="Jerry", replacement={"canonical_field": "unit_standard"})
    db_session.add(proposal); db_session.commit()
    db_session.add(ProposalResolution(proposal_id=proposal.proposal_id, action="reject", resolver="Jerry", reason="Needs more evidence")); db_session.commit()
    assert db_session.scalar(select(func.count()).select_from(ProposalResolution)) == 1


def test_definition_conflict_resolution_is_recorded(db_session) -> None:
    """A mapping-admin prototype decision is retained as a distinct audit event."""
    mapping = seed_mapping_set(db_session)
    from app.db.models import MappingDefinition
    definition = db_session.scalar(select(MappingDefinition).where(MappingDefinition.mapping_set_id == mapping.mapping_set_id))
    assert definition is not None
    db_session.add(MappingConflictResolution(mapping_definition_id=definition.mapping_definition_id, action="resolve_approve", resolver="Jerry", reason="Evidence reviewed")); db_session.commit()
    assert db_session.scalar(select(func.count()).select_from(MappingConflictResolution)) == 1
