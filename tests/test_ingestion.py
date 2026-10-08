"""Integration tests covering snapshot persistence, ingestion, and retention."""

from sqlalchemy import func, select

from app.db.models import IngestionRejection, IngestionRun, RawRecord, SourceSnapshot
from app.ingestion.service import persist_snapshot, run_ingestion
from app.synthetic.generator import generate_snapshot


def test_ingestion_writes_raw_records_and_rejections_idempotently(db_session) -> None:
    """A source row without its business identifier is rejected while duplicates survive."""

    snapshot = generate_snapshot(seed=19, patient_count=12)
    persist_snapshot(db_session, snapshot)
    summary = run_ingestion(db_session)
    assert summary["status"] == "completed"
    assert summary["entities"]["patient"]["rejected_rows"] == 1
    assert summary["entities"]["lab_result"]["raw_rows_written"] == 37
    assert db_session.scalar(select(func.count()).select_from(IngestionRejection)) == 1
    raw_count = db_session.scalar(select(func.count()).select_from(RawRecord))
    assert raw_count == sum(entity["raw_rows_written"] for entity in summary["entities"].values())
    repeated = run_ingestion(db_session)
    assert repeated["ingestion_run_id"] == summary["ingestion_run_id"]
    assert db_session.scalar(select(func.count()).select_from(IngestionRun)) == 1


def test_reseeding_retains_processed_snapshot_and_activates_new_one(db_session) -> None:
    """Historical source/raw records stay inspectable when a new fixture snapshot is selected."""

    original = generate_snapshot(seed=23, patient_count=10)
    persist_snapshot(db_session, original)
    first_summary = run_ingestion(db_session)
    raw_before = db_session.scalar(select(func.count()).select_from(RawRecord))
    replacement = generate_snapshot(seed=24, patient_count=10)
    persist_snapshot(db_session, replacement)
    assert db_session.scalar(select(func.count()).select_from(RawRecord)) == raw_before
    original_run = db_session.get(IngestionRun, first_summary["ingestion_run_id"])
    assert original_run is not None and original_run.status == "completed"
    snapshots = db_session.scalars(select(SourceSnapshot)).all()
    assert {snapshot.status for snapshot in snapshots} == {"active", "inactive"}
    assert next(snapshot for snapshot in snapshots if snapshot.status == "active").source_snapshot_id == replacement.source_snapshot_id
