"""API readiness smoke test."""

from fastapi.testclient import TestClient

from app.api.main import app


def test_health_reports_database_readiness(migrated_database: None) -> None:
    """The health endpoint verifies its database dependency."""

    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_import_api_and_console_never_return_raw_upload_values(migrated_database: None) -> None:
    """The user-facing import path profiles metadata but does not return uploaded values."""
    client = TestClient(app)
    upload = client.post(
        "/imports/uploads",
        files={"file": ("labs.csv", b"patient_id,ALT,patient_name\nP-001,42.1,Jane Example\n", "text/csv")},
    )
    assert upload.status_code == 200
    response = client.get(f"/imports/{upload.json()['id']}/suggestions")
    assert response.status_code == 200
    body = response.text
    assert "Jane Example" not in body
    assert "P-001" not in body
    candidates = client.get(f"/imports/{upload.json()['id']}/candidates")
    assert candidates.status_code == 200
    assert candidates.json()["retrieval_version"] == "local-hybrid-retrieval@1.0.0"
    assert "Jane Example" not in candidates.text
    rerank = client.post(f"/imports/{upload.json()['id']}/rerank")
    assert rerank.status_code == 200
    assert rerank.json()["reranked"] == 0
    assert client.get("/imports/console").status_code == 200


def test_mapping_suggestion_review_is_append_only_and_candidate_bound(migrated_database: None) -> None:
    """Reviewing a suggestion requires a candidate and cannot alter the formal mapping registry."""
    client = TestClient(app)
    upload = client.post(
        "/imports/uploads",
        files={"file": ("labs.csv", b"ALT_VALUE\n42.1\n", "text/csv")},
    ).json()
    suggestion = client.get(f"/imports/{upload['id']}/suggestions").json()["items"][0]
    invalid = client.post(f"/mapping-suggestions/{suggestion['id']}/reviews", json={
        "action": "approved", "reviewer": "Jerry", "target": "patient.source_patient_id", "comment": "not a candidate",
    })
    assert invalid.status_code == 422
    approved = client.post(f"/mapping-suggestions/{suggestion['id']}/reviews", json={
        "action": "approved", "reviewer": "Jerry", "target": "measurement.value_standard", "comment": "Verified with unit.",
    })
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    duplicate = client.post(f"/mapping-suggestions/{suggestion['id']}/reviews", json={
        "action": "rejected", "reviewer": "Jerry", "comment": "Attempt to replace.",
    })
    assert duplicate.status_code == 409
    published = client.post(f"/imports/{upload['id']}/publish-mapping-set")
    assert published.status_code == 200
    assert published.json()["definition_count"] == 1
    assert client.post(f"/imports/{upload['id']}/publish-mapping-set").json() == published.json()


def test_factory_benchmark_rejects_incomplete_or_unconfigured_bundle(migrated_database: None) -> None:
    """The synthetic benchmark refuses arbitrary input and leaks no benchmark answers in errors."""
    client = TestClient(app)
    response = client.post("/benchmarks/factory", json={"jobs": {"Source_Patient": "not-a-job"}})
    assert response.status_code == 422
    assert "Gold Canonical Target" not in response.text
    assert "pat_id" not in response.text
    assert client.get("/benchmarks/console").status_code == 200
