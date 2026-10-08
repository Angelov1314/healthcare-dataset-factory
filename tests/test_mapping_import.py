"""Stage 1 mapping import integration tests."""
import hashlib
from sqlalchemy import func, select

from app.db.models import ImportJob, MappingCandidate, MappingSuggestion, SourceFieldProfile
from app.mapping.service import create_import_job, parse_tabular_upload, retrieve_candidates
from app.mapping.llm import DeepSeekMappingProvider, build_safe_rerank_context
from app.mapping.service import profile_postgres_table


def test_csv_profile_persists_only_safe_metadata_and_alias_suggestions(db_session) -> None:
    """ALT maps by safe alias but a patient name never becomes an example value."""
    content = b"patient_id,ALT,patient_name\nP001,42.1,Jane Example\n"
    table, headers, rows = parse_tabular_upload("labs.csv", content)
    result = create_import_job(db_session, "file", table, headers, rows, hashlib.sha256(content).hexdigest())
    assert result["field_count"] == 3
    assert db_session.scalar(select(func.count()).select_from(ImportJob)) == 1
    summaries = db_session.scalars(select(SourceFieldProfile.safe_summary)).all()
    assert all("Jane" not in str(summary) and "P001" not in str(summary) for summary in summaries)
    suggestions = db_session.scalars(select(MappingSuggestion)).all()
    assert any(x.target_field == "value_standard" and x.route == "vocabulary" for x in suggestions)
    assert any(x.status == "unmapped" for x in suggestions)


def test_excel_profile_is_supported(db_session) -> None:
    """Excel parsing requires a header and produces a profile without raw values."""
    from io import BytesIO
    from openpyxl import Workbook
    book = Workbook(); sheet = book.active; sheet.append(["AST", "unit"]); sheet.append(["31.0", "U/L"])
    buffer = BytesIO(); book.save(buffer)
    table, headers, rows = parse_tabular_upload("results.xlsx", buffer.getvalue())
    result = create_import_job(db_session, "file", table, headers, rows, hashlib.sha256(buffer.getvalue()).hexdigest())
    assert result["suggestion_count"] == 2


def test_postgres_import_rejects_unallowlisted_host(db_session) -> None:
    """The read-only adapter refuses a source host outside configured policy."""
    try:
        profile_postgres_table(db_session, "postgresql+psycopg://reader:secret@untrusted.example:5432/source", "public", "labs", {"localhost"}, {5432}, 100)
        assert False, "expected host policy rejection"
    except ValueError as exc:
        assert "not allowed" in str(exc)


def test_postgres_import_rejects_unallowlisted_port(db_session) -> None:
    """The adapter cannot be redirected to an arbitrary PostgreSQL port."""
    try:
        profile_postgres_table(db_session, "postgresql+psycopg://reader:secret@localhost:15432/source", "public", "labs", {"localhost"}, {5432}, 100)
        assert False, "expected port policy rejection"
    except ValueError as exc:
        assert "port is not allowed" in str(exc)


def test_rules_are_prioritized_exact_then_vocabulary_then_alias(db_session) -> None:
    """The deterministic engine records the selected route rather than blending scores."""
    result = create_import_job(
        db_session, "file", "contract", ["value_standard", "AST", "source_sex", "not_mapped"],
        [["3.2", "18", "female", "x"]], "artifact"
    )
    assert result["suggestion_count"] == 4
    routes = {item.route for item in db_session.scalars(select(MappingSuggestion)).all()}
    assert {"exact", "vocabulary", "alias", "abstain"} <= routes


def test_approved_history_has_priority_over_alias(db_session) -> None:
    """An approved prior mapping wins over a generic field-name alias."""
    result = create_import_job(db_session, "file", "contract", ["patient_id"], [["P001"]], "artifact")
    assert result["suggestion_count"] == 1
    assert db_session.scalar(select(MappingSuggestion)).route == "historical"


def test_hybrid_retrieval_is_local_stable_and_domain_limited(db_session) -> None:
    """Retrieval uses deterministic local scores and avoids irrelevant target domains."""
    first = retrieve_candidates("ALT_VALUE", "decimal", "U/L")
    second = retrieve_candidates("ALT_VALUE", "decimal", "U/L")
    assert first == second
    assert first[0]["domain"] == "measurement"
    assert all(candidate["domain"] == "measurement" for candidate in first)
    create_import_job(db_session, "file", "labs", ["ALT_VALUE"], [["42.1"]], "artifact")
    candidates = db_session.scalars(select(MappingCandidate)).all()
    assert candidates
    assert all(candidate.evidence["retrieval_version"] == "local-hybrid-retrieval@1.0.0" for candidate in candidates)


def test_llm_context_rejects_identifier_fields_and_missing_key_falls_back() -> None:
    """The provider receives only safe metadata and never calls out without a key."""
    assert build_safe_rerank_context(
        {"field": "patient_id", "inferred_type": "string", "unit": None, "safe_summary": {"classification": "metadata_safe"}}, []
    ) is None
    context = build_safe_rerank_context(
        {"field": "ALT_VALUE", "inferred_type": "decimal", "unit": "U/L", "safe_summary": {"classification": "metadata_safe", "non_null_count": 10, "distinct_count": 8, "sample_kind": "decimal"}},
        [{"target": "measurement.value_standard", "domain": "measurement", "rank": 1}],
    )
    assert context is not None
    outcome = DeepSeekMappingProvider("", "https://api.deepseek.com", "deepseek-v4-flash", 1).rerank(context)
    assert outcome.status == "provider_not_configured"
    assert outcome.result is None
