"""Milestone 1 source-zone and raw-zone persistence models."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SourceSnapshot(Base):
    """A deterministic synthetic-source snapshot selected for ingestion."""

    __tablename__ = "source_snapshot"
    __table_args__ = (
        Index("uq_active_synthetic_snapshot", "generator_key", unique=True, postgresql_where=text("status = 'active'")),
        {"schema": "raw"},
    )

    source_snapshot_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    generator_key: Mapped[str] = mapped_column(String(128), nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    patient_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SourceRowMixin:
    """Columns shared by unclean source-system records."""

    source_row_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    source_snapshot_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("raw.source_snapshot.source_snapshot_id"), nullable=False, index=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HisPatient(SourceRowMixin, Base):
    __tablename__ = "patient"
    __table_args__ = (Index("ix_his_patient_business_id", "patient_id"), {"schema": "his_src"})
    patient_id: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str | None] = mapped_column(Text)
    sex: Mapped[str | None] = mapped_column(Text)
    date_of_birth: Mapped[str | None] = mapped_column(Text)
    id_number: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    province: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)


class HisVisit(SourceRowMixin, Base):
    __tablename__ = "visit"
    __table_args__ = (Index("ix_his_visit_business_id", "visit_id"), {"schema": "his_src"})
    visit_id: Mapped[str | None] = mapped_column(Text)
    patient_id: Mapped[str | None] = mapped_column(Text)
    admit_at: Mapped[str | None] = mapped_column(Text)
    discharge_at: Mapped[str | None] = mapped_column(Text)
    department: Mapped[str | None] = mapped_column(Text)
    visit_type: Mapped[str | None] = mapped_column(Text)


class EmrDiagnosis(SourceRowMixin, Base):
    __tablename__ = "diagnosis"
    __table_args__ = (Index("ix_emr_diagnosis_business_id", "diagnosis_id"), {"schema": "emr_src"})
    diagnosis_id: Mapped[str | None] = mapped_column(Text)
    patient_id: Mapped[str | None] = mapped_column(Text)
    visit_id: Mapped[str | None] = mapped_column(Text)
    diagnosis_code: Mapped[str | None] = mapped_column(Text)
    diagnosis_name: Mapped[str | None] = mapped_column(Text)
    diagnosis_at: Mapped[str | None] = mapped_column(Text)


class EmrProcedure(SourceRowMixin, Base):
    __tablename__ = "procedure"
    __table_args__ = (Index("ix_emr_procedure_business_id", "procedure_id"), {"schema": "emr_src"})
    procedure_id: Mapped[str | None] = mapped_column(Text)
    patient_id: Mapped[str | None] = mapped_column(Text)
    visit_id: Mapped[str | None] = mapped_column(Text)
    procedure_code: Mapped[str | None] = mapped_column(Text)
    procedure_name: Mapped[str | None] = mapped_column(Text)
    procedure_at: Mapped[str | None] = mapped_column(Text)


class EmrMedication(SourceRowMixin, Base):
    __tablename__ = "medication"
    __table_args__ = (Index("ix_emr_medication_business_id", "medication_id"), {"schema": "emr_src"})
    medication_id: Mapped[str | None] = mapped_column(Text)
    patient_id: Mapped[str | None] = mapped_column(Text)
    visit_id: Mapped[str |None] = mapped_column(Text)
    drug_code: Mapped[str | None] = mapped_column(Text)
    drug_name: Mapped[str | None] = mapped_column(Text)
    dose: Mapped[str | None] = mapped_column(Text)
    dose_unit: Mapped[str | None] = mapped_column(Text)
    start_at: Mapped[str | None] = mapped_column(Text)
    end_at: Mapped[str | None] = mapped_column(Text)


class EmrOutcome(SourceRowMixin, Base):
    __tablename__ = "outcome"
    __table_args__ = (Index("ix_emr_outcome_patient_visit", "patient_id", "visit_id"), {"schema": "emr_src"})
    patient_id: Mapped[str | None] = mapped_column(Text)
    visit_id: Mapped[str | None] = mapped_column(Text)
    transplant_flag: Mapped[str | None] = mapped_column(Text)
    death_flag: Mapped[str | None] = mapped_column(Text)
    followup_days: Mapped[str | None] = mapped_column(Text)


class LisLabResult(SourceRowMixin, Base):
    __tablename__ = "lab_result"
    __table_args__ = (Index("ix_lis_lab_business_id", "lab_result_id"), {"schema": "lis_src"})
    lab_result_id: Mapped[str | None] = mapped_column(Text)
    patient_id: Mapped[str | None] = mapped_column(Text)
    visit_id: Mapped[str | None] = mapped_column(Text)
    test_code: Mapped[str | None] = mapped_column(Text)
    test_name: Mapped[str | None] = mapped_column(Text)
    value: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(Text)
    reference_low: Mapped[str | None] = mapped_column(Text)
    reference_high: Mapped[str | None] = mapped_column(Text)
    measured_at: Mapped[str | None] = mapped_column(Text)


class IngestionRun(Base):
    __tablename__ = "ingestion_run"
    __table_args__ = ({"schema": "raw"},)
    ingestion_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    source_snapshot_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("raw.source_snapshot.source_snapshot_id"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class RawRecord(Base):
    __tablename__ = "record"
    __table_args__ = (
        UniqueConstraint("source_system", "source_entity", "source_row_id", "ingestion_run_id", name="uq_raw_record_run_source"),
        {"schema": "raw"},
    )
    raw_record_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    ingestion_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("raw.ingestion_run.ingestion_run_id"), nullable=False)
    source_system: Mapped[str] = mapped_column(String(16), nullable=False)
    source_entity: Mapped[str] = mapped_column(String(32), nullable=False)
    source_row_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IngestionRejection(Base):
    __tablename__ = "ingestion_rejection"
    __table_args__ = ({"schema": "raw"},)
    rejection_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    ingestion_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("raw.ingestion_run.ingestion_run_id"), nullable=False)
    source_system: Mapped[str] = mapped_column(String(16), nullable=False)
    source_entity: Mapped[str] = mapped_column(String(32), nullable=False)
    source_row_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    error_code: Mapped[str] = mapped_column(String(64), nullable=False)
    field_name: Mapped[str | None] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    rejected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MappingSet(Base):
    __tablename__ = "mapping_set"
    __table_args__ = (UniqueConstraint("scope", "version", name="uq_mapping_set_scope_version"), {"schema": "governance"})
    mapping_set_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MappingDefinition(Base):
    __tablename__ = "mapping_definition"
    __table_args__ = (UniqueConstraint("mapping_set_id", "source_system", "source_entity", "source_field", "canonical_entity", "canonical_field", name="uq_mapping_definition_target"), {"schema": "governance"})
    mapping_definition_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    mapping_set_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("governance.mapping_set.mapping_set_id"), nullable=False)
    source_system: Mapped[str] = mapped_column(String(16), nullable=False)
    source_entity: Mapped[str] = mapped_column(String(32), nullable=False)
    source_field: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_entity: Mapped[str] = mapped_column(String(32), nullable=False)
    canonical_field: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_key: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reviewer: Mapped[str] = mapped_column(String(128), nullable=False, default="system")


class CanonicalizationRun(Base):
    __tablename__ = "canonicalization_run"
    __table_args__ = (UniqueConstraint("ingestion_run_id", "mapping_set_id", name="uq_canonical_run_input_mapping"), {"schema": "governance"})
    canonicalization_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    source_snapshot_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("raw.source_snapshot.source_snapshot_id"), nullable=False)
    ingestion_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("raw.ingestion_run.ingestion_run_id"), nullable=False)
    mapping_set_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("governance.mapping_set.mapping_set_id"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CanonicalPatient(Base):
    __tablename__ = "patient"
    __table_args__ = (UniqueConstraint("canonicalization_run_id", "canonical_patient_id", name="uq_canonical_patient_run_id"), {"schema": "canonical"})
    canonical_row_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    canonicalization_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("governance.canonicalization_run.canonicalization_run_id"), nullable=False)
    canonical_patient_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source_patient_id: Mapped[str] = mapped_column(Text, nullable=False)
    sex_standard: Mapped[str] = mapped_column(String(16), nullable=False)
    date_of_birth: Mapped[str | None] = mapped_column(String(10))
    age: Mapped[int | None] = mapped_column(Integer)
    province: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)


class CanonicalMeasurement(Base):
    __tablename__ = "measurement"
    __table_args__ = ({"schema": "canonical"},)
    canonical_row_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    canonicalization_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("governance.canonicalization_run.canonicalization_run_id"), nullable=False)
    canonical_patient_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source_row_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source_visit_id: Mapped[str | None] = mapped_column(Text)
    measured_at: Mapped[str | None] = mapped_column(String(10))
    normalized_test_code: Mapped[str | None] = mapped_column(String(32))
    normalized_test_name: Mapped[str | None] = mapped_column(String(64))
    value_original: Mapped[str | None] = mapped_column(Text)
    unit_original: Mapped[str | None] = mapped_column(Text)
    value_standard: Mapped[float | None] = mapped_column(nullable=True)
    unit_standard: Mapped[str | None] = mapped_column(String(32))


class CanonicalVisit(Base):
    __tablename__ = "visit"
    __table_args__ = ({"schema": "canonical"},)
    canonical_row_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    canonicalization_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("governance.canonicalization_run.canonicalization_run_id"), nullable=False)
    source_row_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source_visit_id: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_patient_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    admit_at: Mapped[str | None] = mapped_column(Text)
    discharge_at: Mapped[str | None] = mapped_column(Text)
    department: Mapped[str | None] = mapped_column(Text)
    visit_type: Mapped[str | None] = mapped_column(Text)


class CanonicalCondition(Base):
    __tablename__ = "condition"
    __table_args__ = ({"schema": "canonical"},)
    canonical_row_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    canonicalization_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("governance.canonicalization_run.canonicalization_run_id"), nullable=False)
    source_row_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    canonical_patient_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source_visit_id: Mapped[str | None] = mapped_column(Text)
    source_code: Mapped[str | None] = mapped_column(Text)
    source_name: Mapped[str | None] = mapped_column(Text)
    normalized_code: Mapped[str | None] = mapped_column(Text)
    normalized_name: Mapped[str | None] = mapped_column(Text)


class QualityRun(Base):
    __tablename__ = "quality_run"
    __table_args__ = ({"schema": "governance"},)
    quality_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    ingestion_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("raw.ingestion_run.ingestion_run_id"), nullable=False)
    canonicalization_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("governance.canonicalization_run.canonicalization_run_id"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    report: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class QualityResult(Base):
    __tablename__ = "quality_result"
    __table_args__ = ({"schema": "governance"},)
    quality_result_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    quality_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("governance.quality_run.quality_run_id"), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(32), nullable=False)
    phase: Mapped[str] = mapped_column(String(16), nullable=False)
    dimension: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    observed: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class LineageEvent(Base):
    __tablename__ = "lineage_event"
    __table_args__ = ({"schema": "governance"},)
    lineage_event_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    canonicalization_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("governance.canonicalization_run.canonicalization_run_id"), nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    outputs: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    versions: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class MappingReview(Base):
    __tablename__ = "mapping_review"
    __table_args__ = ({"schema": "governance"},)
    review_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    mapping_definition_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("governance.mapping_definition.mapping_definition_id"), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    reviewer: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class FieldLineage(Base):
    __tablename__ = "field_lineage"
    __table_args__ = ({"schema": "governance"},)
    field_lineage_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    canonicalization_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("governance.canonicalization_run.canonicalization_run_id"), nullable=False)
    canonical_record_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    canonical_entity: Mapped[str] = mapped_column(String(32), nullable=False)
    canonical_field: Mapped[str] = mapped_column(String(64), nullable=False)
    source_row_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source_entity: Mapped[str] = mapped_column(String(32), nullable=False)
    source_field: Mapped[str] = mapped_column(String(64), nullable=False)
    mapping_definition_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    transform_version: Mapped[str] = mapped_column(String(64), nullable=False)

class MappingProposal(Base):
    __tablename__ = "mapping_proposal"
    __table_args__ = ({"schema": "governance"},)
    proposal_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    mapping_definition_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("governance.mapping_definition.mapping_definition_id"), nullable=False)
    proposer: Mapped[str] = mapped_column(String(128), nullable=False)
    replacement: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class ProposalResolution(Base):
    __tablename__ = "proposal_resolution"
    __table_args__ = (UniqueConstraint("proposal_id", name="uq_proposal_resolution"), {"schema": "governance"})
    resolution_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    proposal_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("governance.mapping_proposal.proposal_id"), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    resolver: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class MappingConflictResolution(Base):
    __tablename__ = "mapping_conflict_resolution"
    __table_args__ = ({"schema": "governance"},)
    resolution_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    mapping_definition_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("governance.mapping_definition.mapping_definition_id"), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    resolver: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class OmopMappingRun(Base):
    """Immutable, reproducible canonical-to-OMOP-lite mapping execution."""

    __tablename__ = "mapping_run"
    __table_args__ = (UniqueConstraint("canonicalization_run_id", "manifest_hash", "attempt_number", name="uq_omop_mapping_attempt"), {"schema": "omop"})
    omop_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    canonicalization_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("governance.canonicalization_run.canonicalization_run_id"), nullable=False)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OmopPerson(Base):
    __tablename__ = "person"
    __table_args__ = (UniqueConstraint("omop_run_id", "canonical_patient_id", name="uq_omop_person_run_patient"), {"schema": "omop"})
    person_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    omop_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("omop.mapping_run.omop_run_id"), nullable=False)
    canonical_patient_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    gender_concept_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    year_of_birth: Mapped[int | None] = mapped_column(Integer)


class OmopVisitOccurrence(Base):
    __tablename__ = "visit_occurrence"
    __table_args__ = (UniqueConstraint("omop_run_id", "source_row_id", name="uq_omop_visit_source"), {"schema": "omop"})
    visit_occurrence_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    omop_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("omop.mapping_run.omop_run_id"), nullable=False)
    canonical_row_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source_row_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    canonical_patient_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source_visit_id: Mapped[str] = mapped_column(Text, nullable=False)
    visit_concept_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    visit_start_date: Mapped[str | None] = mapped_column(String(10))
    visit_end_date: Mapped[str | None] = mapped_column(String(10))


class OmopConditionOccurrence(Base):
    __tablename__ = "condition_occurrence"
    __table_args__ = (UniqueConstraint("omop_run_id", "source_row_id", name="uq_omop_condition_source"), {"schema": "omop"})
    condition_occurrence_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    omop_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("omop.mapping_run.omop_run_id"), nullable=False)
    canonical_row_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source_row_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    canonical_patient_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source_visit_id: Mapped[str | None] = mapped_column(Text)
    condition_concept_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    condition_source_value: Mapped[str | None] = mapped_column(Text)


class OmopMeasurement(Base):
    __tablename__ = "measurement"
    __table_args__ = (UniqueConstraint("omop_run_id", "source_row_id", name="uq_omop_measurement_source"), {"schema": "omop"})
    measurement_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    omop_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("omop.mapping_run.omop_run_id"), nullable=False)
    canonical_row_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source_row_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    canonical_patient_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source_visit_id: Mapped[str | None] = mapped_column(Text)
    measurement_concept_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    value_as_number: Mapped[float | None] = mapped_column(nullable=True)
    unit_source_value: Mapped[str | None] = mapped_column(String(32))
    measurement_date: Mapped[str | None] = mapped_column(String(10))


class OmopDrugExposure(Base):
    """Raw-EMR adapter mapping; a future milestone can canonicalize medication first."""

    __tablename__ = "drug_exposure"
    __table_args__ = (UniqueConstraint("omop_run_id", "source_row_id", name="uq_omop_drug_source"), {"schema": "omop"})
    drug_exposure_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    omop_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("omop.mapping_run.omop_run_id"), nullable=False)
    source_row_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    canonical_patient_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source_visit_id: Mapped[str | None] = mapped_column(Text)
    drug_concept_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    drug_source_value: Mapped[str | None] = mapped_column(Text)


class OmopProcedureOccurrence(Base):
    """Raw-EMR adapter mapping with explicit OMOP-lite procedure domain."""

    __tablename__ = "procedure_occurrence"
    __table_args__ = (UniqueConstraint("omop_run_id", "source_row_id", name="uq_omop_procedure_source"), {"schema": "omop"})
    procedure_occurrence_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    omop_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("omop.mapping_run.omop_run_id"), nullable=False)
    source_row_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    canonical_patient_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source_visit_id: Mapped[str | None] = mapped_column(Text)
    procedure_concept_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    procedure_source_value: Mapped[str | None] = mapped_column(Text)


class OmopMappingRejection(Base):
    __tablename__ = "mapping_rejection"
    __table_args__ = ({"schema": "omop"},)
    rejection_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    omop_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("omop.mapping_run.omop_run_id"), nullable=False)
    source_row_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)


class CohortDefinition(Base):
    __tablename__ = "definition"
    __table_args__ = (UniqueConstraint("slug", "version", name="uq_cohort_version"), {"schema": "cohort"})
    cohort_definition_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    parent_definition_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    condition_tree: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    condition_tree_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    time_window: Mapped[str] = mapped_column(String(32), nullable=False, default="all_time")
    creator: Mapped[str] = mapped_column(String(128), nullable=False, default="system")
    evaluator_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0.0")


class CohortRun(Base):
    __tablename__ = "run"
    __table_args__ = (UniqueConstraint("cohort_definition_id", "omop_run_id", "attempt_number", name="uq_cohort_run_attempt"), {"schema": "cohort"})
    cohort_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    cohort_definition_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("cohort.definition.cohort_definition_id"), nullable=False)
    omop_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("omop.mapping_run.omop_run_id"), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    member_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lineage: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class CohortMember(Base):
    __tablename__ = "member"
    __table_args__ = (UniqueConstraint("cohort_run_id", "canonical_patient_id", name="uq_cohort_member_patient"), {"schema": "cohort"})
    cohort_member_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    cohort_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("cohort.run.cohort_run_id"), nullable=False)
    canonical_patient_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)


class PrivacyPolicy(Base):
    """Append-only product privacy configuration; it stores no secret material."""
    __tablename__ = "privacy_policy"
    __table_args__ = (UniqueConstraint("slug", "version", name="uq_privacy_policy_version"), {"schema": "product"})
    privacy_policy_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    policy: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    policy_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    key_id: Mapped[str] = mapped_column(String(64), nullable=False)


class DatasetProduct(Base):
    """Logical, immutable identity of a cohort-derived product."""
    __tablename__ = "dataset_product"
    __table_args__ = (UniqueConstraint("slug", "version", "cohort_run_id", "quality_run_id", "privacy_policy_id", name="uq_product_identity"), {"schema": "product"})
    dataset_product_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    cohort_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("cohort.run.cohort_run_id"), nullable=False)
    quality_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("governance.quality_run.quality_run_id"), nullable=False)
    privacy_policy_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("product.privacy_policy.privacy_policy_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProductExportAttempt(Base):
    """Audited artifact build with count-only metadata and stable hashes."""
    __tablename__ = "export_attempt"
    __table_args__ = (UniqueConstraint("dataset_product_id", "attempt_number", name="uq_product_attempt"), {"schema": "product"})
    export_attempt_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    dataset_product_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("product.dataset_product.dataset_product_id"), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    patient_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    csv_path: Mapped[str | None] = mapped_column(Text)
    card_path: Mapped[str | None] = mapped_column(Text)
    csv_hash: Mapped[str | None] = mapped_column(String(64))
    card_hash: Mapped[str | None] = mapped_column(String(64))
    card: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    lineage: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class ImportJob(Base):
    """Metadata-only external import profile; source records are never exposed by this model."""
    __tablename__ = "import_job"
    __table_args__ = ({"schema": "mapping"},)
    import_job_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    source_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    artifact_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    profile_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SourceFieldProfile(Base):
    """Safe source schema metadata and synthetic/redacted value summary."""
    __tablename__ = "source_field_profile"
    __table_args__ = (UniqueConstraint("import_job_id", "table_name", "field_name", name="uq_import_profile_field"), {"schema": "mapping"})
    source_field_profile_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    import_job_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("mapping.import_job.import_job_id"), nullable=False)
    table_name: Mapped[str] = mapped_column(String(128), nullable=False)
    field_name: Mapped[str] = mapped_column(String(128), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    inferred_type: Mapped[str] = mapped_column(String(32), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(32))
    safe_summary: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class MappingSuggestion(Base):
    """A non-executable candidate mapping requiring policy/review resolution."""
    __tablename__ = "mapping_suggestion"
    __table_args__ = ({"schema": "mapping"},)
    mapping_suggestion_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    import_job_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("mapping.import_job.import_job_id"), nullable=False)
    source_field_profile_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("mapping.source_field_profile.source_field_profile_id"), nullable=False)
    route: Mapped[str] = mapped_column(String(32), nullable=False)
    target_entity: Mapped[str | None] = mapped_column(String(64))
    target_field: Mapped[str | None] = mapped_column(String(64))
    confidence: Mapped[float] = mapped_column(nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)


class MappingCandidate(Base):
    """Locally retrieved target candidate with deterministic score evidence."""
    __tablename__ = "mapping_candidate"
    __table_args__ = (UniqueConstraint("mapping_suggestion_id", "target_entity", "target_field", name="uq_mapping_candidate_target"), {"schema": "mapping"})
    mapping_candidate_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    mapping_suggestion_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("mapping.mapping_suggestion.mapping_suggestion_id"), nullable=False)
    domain: Mapped[str] = mapped_column(String(32), nullable=False)
    target_entity: Mapped[str] = mapped_column(String(64), nullable=False)
    target_field: Mapped[str] = mapped_column(String(64), nullable=False)
    bm25_score: Mapped[float] = mapped_column(Float, nullable=False)
    dense_score: Mapped[float] = mapped_column(Float, nullable=False)
    fusion_score: Mapped[float] = mapped_column(Float, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class MappingRerankAttempt(Base):
    """Append-only optional LLM rerank provenance; no prompt or raw response is stored."""
    __tablename__ = "mapping_rerank_attempt"
    __table_args__ = ({"schema": "mapping"},)
    mapping_rerank_attempt_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    mapping_suggestion_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("mapping.mapping_suggestion.mapping_suggestion_id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    context_hash: Mapped[str | None] = mapped_column(String(64))
    response_hash: Mapped[str | None] = mapped_column(String(64))
    outcome: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MappingSuggestionReview(Base):
    """One append-only human decision for an imported mapping suggestion."""
    __tablename__ = "mapping_suggestion_review"
    __table_args__ = (UniqueConstraint("mapping_suggestion_id", name="uq_mapping_suggestion_review"), {"schema": "mapping"})
    mapping_suggestion_review_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    mapping_suggestion_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("mapping.mapping_suggestion.mapping_suggestion_id"), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    reviewer: Mapped[str] = mapped_column(String(128), nullable=False)
    target_entity: Mapped[str | None] = mapped_column(String(64))
    target_field: Mapped[str | None] = mapped_column(String(64))
    transform: Mapped[str] = mapped_column(String(64), nullable=False, default="identity")
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FactoryBenchmarkRun(Base):
    """Immutable synthetic-fixture benchmark run with aggregate-only report."""
    __tablename__ = "factory_benchmark_run"
    __table_args__ = ({"schema": "mapping"},)
    factory_benchmark_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    registry_version: Mapped[str] = mapped_column(String(64), nullable=False)
    registry_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    retrieval_version: Mapped[str] = mapped_column(String(64), nullable=False)
    gold_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    bundle_manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    metric_policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    report: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FactoryBenchmarkProfileSnapshot(Base):
    """Immutable safe profile snapshot used by one factory benchmark run."""
    __tablename__ = "factory_benchmark_profile_snapshot"
    __table_args__ = ({"schema": "mapping"},)
    factory_benchmark_profile_snapshot_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    factory_benchmark_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("mapping.factory_benchmark_run.factory_benchmark_run_id"), nullable=False)
    source_field_profile_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("mapping.source_field_profile.source_field_profile_id"), nullable=False)
    source_sheet: Mapped[str] = mapped_column(String(128), nullable=False)
    field_name: Mapped[str] = mapped_column(String(128), nullable=False)
    profile_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class FactoryBenchmarkCandidateSnapshot(Base):
    """Immutable local candidate ranking for a factory benchmark profile snapshot."""
    __tablename__ = "factory_benchmark_candidate_snapshot"
    __table_args__ = (UniqueConstraint("factory_benchmark_profile_snapshot_id", "target", name="uq_factory_benchmark_candidate_target"), {"schema": "mapping"})
    factory_benchmark_candidate_snapshot_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    factory_benchmark_profile_snapshot_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("mapping.factory_benchmark_profile_snapshot.factory_benchmark_profile_snapshot_id"), nullable=False)
    target: Mapped[str] = mapped_column(String(128), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    bm25_score: Mapped[float] = mapped_column(Float, nullable=False)
    dense_score: Mapped[float] = mapped_column(Float, nullable=False)
    fusion_score: Mapped[float] = mapped_column(Float, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class MappingImportAuditEvent(Base):
    """Append-only profile and suggestion provenance, without raw source values."""
    __tablename__ = "import_audit_event"
    __table_args__ = ({"schema": "mapping"},)
    import_audit_event_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    import_job_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("mapping.import_job.import_job_id"), nullable=False)
    mapping_suggestion_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("mapping.mapping_suggestion.mapping_suggestion_id"))
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
