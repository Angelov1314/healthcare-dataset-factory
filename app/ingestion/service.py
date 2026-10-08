"""Persist synthetic source snapshots and ingest them without transformations."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import (
    EmrDiagnosis, EmrMedication, EmrOutcome, EmrProcedure, HisPatient, HisVisit,
    IngestionRejection, IngestionRun, LisLabResult, RawRecord, SourceSnapshot,
)
from app.synthetic.generator import SourceRecord, SyntheticSnapshot

ENTITY_MODELS = {
    "patient": HisPatient, "visit": HisVisit, "diagnosis": EmrDiagnosis,
    "procedure": EmrProcedure, "medication": EmrMedication, "outcome": EmrOutcome,
    "lab_result": LisLabResult,
}
REQUIRED_BUSINESS_FIELDS = {
    "patient": "patient_id", "visit": "visit_id", "diagnosis": "diagnosis_id",
    "procedure": "procedure_id", "medication": "medication_id", "outcome": "visit_id",
    "lab_result": "lab_result_id",
}


def persist_snapshot(session: Session, snapshot: SyntheticSnapshot) -> dict[str, int]:
    """Store a generated snapshot and make it the active synthetic snapshot."""

    session.execute(update(SourceSnapshot).where(SourceSnapshot.generator_key == "synthetic").values(status="inactive"))
    manifest = session.get(SourceSnapshot, snapshot.source_snapshot_id)
    if manifest is None:
        manifest = SourceSnapshot(
            source_snapshot_id=snapshot.source_snapshot_id, generator_key="synthetic", seed=snapshot.seed,
            patient_count=snapshot.patient_count, status="active",
        )
        session.add(manifest)
    else:
        manifest.status = "active"
    inserted: Counter[str] = Counter()
    for entity, source_records in snapshot.records.items():
        model = ENTITY_MODELS[entity]
        for record in source_records:
            if session.get(model, record.source_row_id) is None:
                session.add(model(source_row_id=record.source_row_id, source_snapshot_id=snapshot.source_snapshot_id,
                                  payload=record.payload, **record.payload))
                inserted[entity] += 1
    session.commit()
    return dict(inserted)


def active_snapshot_id(session: Session) -> UUID:
    """Return the sole active synthetic snapshot or raise a useful error."""

    snapshot_id = session.scalar(select(SourceSnapshot.source_snapshot_id).where(SourceSnapshot.status == "active"))
    if snapshot_id is None:
        raise ValueError("No active synthetic source snapshot. Run the seed command first.")
    return snapshot_id


def _validation_error(record: SourceRecord) -> tuple[str, str, str] | None:
    business_field = REQUIRED_BUSINESS_FIELDS[record.source_entity]
    if not record.payload.get(business_field):
        return ("missing_business_identifier", business_field, f"Required field {business_field} is missing")
    return None


def run_ingestion(session: Session, snapshot_id: UUID | None = None, new_run: bool = False) -> dict[str, Any]:
    """Validate and load one source snapshot into raw envelopes and rejections."""

    selected_snapshot_id = snapshot_id or active_snapshot_id(session)
    if not new_run:
        completed = session.scalar(
            select(IngestionRun).where(
                IngestionRun.source_snapshot_id == selected_snapshot_id, IngestionRun.status == "completed"
            ).order_by(IngestionRun.started_at.desc())
        )
        if completed is not None:
            return completed.summary or {"ingestion_run_id": str(completed.ingestion_run_id), "status": "completed"}

    run = IngestionRun(ingestion_run_id=uuid4(), source_snapshot_id=selected_snapshot_id, status="started")
    session.add(run)
    session.commit()
    summary: dict[str, Any] = {"ingestion_run_id": str(run.ingestion_run_id), "source_snapshot_id": str(selected_snapshot_id),
                               "status": "started", "entities": {}}
    try:
        for entity, model in ENTITY_MODELS.items():
            seen = written = rejected = 0
            error_counts: Counter[str] = Counter()
            rows = session.scalars(select(model).where(model.source_snapshot_id == selected_snapshot_id)).all()
            for row in rows:
                seen += 1
                record = SourceRecord(source_system={"patient": "his", "visit": "his", "lab_result": "lis"}.get(entity, "emr"),
                                      source_entity=entity, source_row_id=row.source_row_id, payload=row.payload)
                error = _validation_error(record)
                if error:
                    code, field, reason = error
                    session.add(IngestionRejection(ingestion_run_id=run.ingestion_run_id, source_system=record.source_system,
                        source_entity=entity, source_row_id=row.source_row_id, error_code=code, field_name=field,
                        reason=reason, payload=row.payload))
                    rejected += 1
                    error_counts[code] += 1
                else:
                    session.add(RawRecord(ingestion_run_id=run.ingestion_run_id, source_system=record.source_system,
                        source_entity=entity, source_row_id=row.source_row_id, payload=row.payload))
                    written += 1
            session.commit()
            summary["entities"][entity] = {"source_rows_seen": seen, "raw_rows_written": written,
                                            "rejected_rows": rejected, "rejections_by_code": dict(error_counts)}
        summary["status"] = "completed"
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        run.summary = summary
        session.commit()
        return summary
    except Exception:
        session.rollback()
        failed = session.get(IngestionRun, run.ingestion_run_id)
        if failed is not None:
            failed.status = "failed"
            failed.completed_at = datetime.now(timezone.utc)
            session.commit()
        raise
