"""Deterministic, local-vocabulary canonical-to-OMOP-lite mapping."""
from __future__ import annotations

import hashlib
import json
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    CanonicalCondition, CanonicalMeasurement, CanonicalPatient, CanonicalVisit,
    CanonicalizationRun, OmopConditionOccurrence, OmopDrugExposure,
    OmopMappingRejection, OmopMappingRun, OmopMeasurement, OmopPerson,
    OmopProcedureOccurrence, OmopVisitOccurrence, RawRecord,
)

RULE_VERSION = "HDF_LOCAL@1.0.0"
MANIFEST = {
    "catalog": RULE_VERSION,
    "gender": {"male": 1, "female": 2},
    "measurement": {"ALT": 1001, "AST": 1002, "TBIL": 1003},
    "condition": {"K74.6": 1101, "B18.1": 1102, "K72.9": 1103},
    "drug": {"Entecavir": 2001},
    "procedure": {"89.01": 3001},
    "visit": {"inpatient": 4001, "outpatient": 4002},
}


def manifest_hash() -> str:
    """Return the stable hash of the rule manifest used by every mapping run."""
    payload = json.dumps(MANIFEST, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _year(value: str | None) -> int | None:
    try:
        return int((value or "")[:4])
    except ValueError:
        return None


def run_omop_mapping(session: Session, canonicalization_run_id: UUID, retry: bool = False) -> dict[str, object]:
    """Map a completed canonical run into local OMOP-lite tables idempotently."""
    canonical_run = session.get(CanonicalizationRun, canonicalization_run_id)
    if canonical_run is None or canonical_run.status != "completed":
        raise ValueError("Completed canonicalization run required")
    digest = manifest_hash()
    previous = session.scalars(select(OmopMappingRun).where(
        OmopMappingRun.canonicalization_run_id == canonicalization_run_id,
        OmopMappingRun.manifest_hash == digest,
    ).order_by(OmopMappingRun.attempt_number.desc())).first()
    if previous and previous.status == "completed":
        return previous.summary or {"id": str(previous.omop_run_id), "status": "completed"}
    if previous and previous.status == "started":
        raise RuntimeError("OMOP mapping already running")
    if previous and previous.status == "failed" and not retry:
        raise ValueError("Failed OMOP mapping requires retry=true")
    attempt = (previous.attempt_number + 1) if previous else 1
    run = OmopMappingRun(canonicalization_run_id=canonicalization_run_id, manifest=MANIFEST,
        manifest_hash=digest, rule_version=RULE_VERSION, attempt_number=attempt, status="started")
    session.add(run); session.flush()
    patients = session.scalars(select(CanonicalPatient).where(CanonicalPatient.canonicalization_run_id == canonicalization_run_id)).all()
    visits = session.scalars(select(CanonicalVisit).where(CanonicalVisit.canonicalization_run_id == canonicalization_run_id)).all()
    conditions = session.scalars(select(CanonicalCondition).where(CanonicalCondition.canonicalization_run_id == canonicalization_run_id)).all()
    measurements = session.scalars(select(CanonicalMeasurement).where(CanonicalMeasurement.canonicalization_run_id == canonicalization_run_id)).all()
    patient_ids = {p.source_patient_id: p.canonical_patient_id for p in patients}
    for row in patients:
        session.add(OmopPerson(omop_run_id=run.omop_run_id, canonical_patient_id=row.canonical_patient_id,
            gender_concept_id=MANIFEST["gender"].get(row.sex_standard, 0), year_of_birth=_year(row.date_of_birth)))
    for row in visits:
        session.add(OmopVisitOccurrence(omop_run_id=run.omop_run_id, canonical_row_id=row.canonical_row_id,
            source_row_id=row.source_row_id, canonical_patient_id=row.canonical_patient_id, source_visit_id=row.source_visit_id,
            visit_concept_id=MANIFEST["visit"].get(row.visit_type or "", 0), visit_start_date=row.admit_at, visit_end_date=row.discharge_at))
    for row in conditions:
        session.add(OmopConditionOccurrence(omop_run_id=run.omop_run_id, canonical_row_id=row.canonical_row_id,
            source_row_id=row.source_row_id, canonical_patient_id=row.canonical_patient_id, source_visit_id=row.source_visit_id,
            condition_concept_id=MANIFEST["condition"].get(row.normalized_code or "", 0), condition_source_value=row.source_code))
    for row in measurements:
        session.add(OmopMeasurement(omop_run_id=run.omop_run_id, canonical_row_id=row.canonical_row_id,
            source_row_id=row.source_row_id, canonical_patient_id=row.canonical_patient_id, source_visit_id=row.source_visit_id,
            measurement_concept_id=MANIFEST["measurement"].get(row.normalized_test_code or "", 0),
            value_as_number=row.value_standard, unit_source_value=row.unit_standard, measurement_date=row.measured_at))
    raw_rows = session.scalars(select(RawRecord).where(RawRecord.ingestion_run_id == canonical_run.ingestion_run_id,
        RawRecord.source_entity.in_(("medication", "procedure")))).all()
    for row in raw_rows:
        payload = row.payload; event_type = row.source_entity
        patient_id = patient_ids.get(payload.get("patient_id") or "")
        visit_id = payload.get("visit_id")
        if patient_id is None or not visit_id:
            session.add(OmopMappingRejection(omop_run_id=run.omop_run_id, source_row_id=row.source_row_id, event_type=event_type, reason="missing_patient_or_visit_join")); continue
        if event_type == "medication":
            session.add(OmopDrugExposure(omop_run_id=run.omop_run_id, source_row_id=row.source_row_id,
                canonical_patient_id=patient_id, source_visit_id=visit_id,
                drug_concept_id=MANIFEST["drug"].get(payload.get("drug_name") or "", 0), drug_source_value=payload.get("drug_name")))
        else:
            session.add(OmopProcedureOccurrence(omop_run_id=run.omop_run_id, source_row_id=row.source_row_id,
                canonical_patient_id=patient_id, source_visit_id=visit_id,
                procedure_concept_id=MANIFEST["procedure"].get(payload.get("procedure_code") or "", 0), procedure_source_value=payload.get("procedure_code")))
    summary = {"id": str(run.omop_run_id), "status": "completed", "manifest_hash": digest,
        "persons": len(patients), "visits": len(visits), "conditions": len(conditions), "measurements": len(measurements),
        "adapter_events": len(raw_rows)}
    run.status = "completed"; run.summary = summary
    session.commit()
    return summary
