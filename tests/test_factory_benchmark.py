"""Factory benchmark registry and leakage-boundary tests."""
from app.mapping.benchmark import factory_candidates
from app.mapping.factory_registry import registry_entries, registry_fingerprint


def test_factory_registry_is_stable_and_target_only() -> None:
    """The benchmark has 116 unique canonical targets and a deterministic fingerprint."""
    entries = registry_entries()
    assert len(entries) == 116
    assert len({item["target"] for item in entries}) == 116
    assert registry_fingerprint() == registry_fingerprint()
    assert all("pat_id" not in item["description"] and "dx_code" not in item["description"] for item in entries)


def test_factory_retrieval_is_local_and_registry_scoped() -> None:
    """A factory candidate request cannot return liver-registry-only targets or source examples."""
    first = factory_candidates("result_val", "decimal", "U/L")
    second = factory_candidates("result_val", "decimal", "U/L")
    targets = {item["target"] for item in registry_entries()}
    assert first == second
    assert first
    assert all(item["target"] in targets for item in first)
    assert all("source_patient_id" not in item["target"] for item in first)
