"""Tests for deterministic, visibly dirty synthetic source data."""

from app.synthetic.generator import generate_snapshot


def test_snapshot_is_deterministic_and_contains_dirty_data() -> None:
    """The same configuration must create stable source records and known defects."""

    first = generate_snapshot(seed=17, patient_count=12)
    second = generate_snapshot(seed=17, patient_count=12)
    assert first.source_snapshot_id == second.source_snapshot_id
    assert first.records == second.records
    patients = first.records["patient"]
    labs = first.records["lab_result"]
    assert patients[0].payload["patient_id"] == patients[1].payload["patient_id"]
    assert patients[3].payload["patient_id"] is None
    assert patients[2].payload["date_of_birth"] == "2035-01-01"
    assert any(row.payload["value"] == "-12.0" for row in labs)
    assert sum(row.payload["lab_result_id"] == "L0000090" for row in labs) == 2
