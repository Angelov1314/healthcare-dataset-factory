"""Stage 1: safe profiling and deterministic source-to-canonical suggestions."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
from urllib.parse import urlparse
from collections.abc import Iterable
from uuid import UUID

from openpyxl import load_workbook
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import Session

from app.db.models import ImportJob, MappingCandidate, MappingDefinition, MappingImportAuditEvent, MappingSuggestion, SourceFieldProfile

VOCABULARY_ALIASES = {
    "alt": ("measurement", "value_standard", "ALT"),
    "gpt": ("measurement", "value_standard", "ALT"),
    "ast": ("measurement", "value_standard", "AST"),
    "tbil": ("measurement", "value_standard", "TBIL"),
}
ALIASES = {
    "patient_id": ("patient", "source_patient_id", None),
    "visit_id": ("visit", "source_visit_id", None),
    "diagnosis_code": ("condition", "normalized_code", None),
    "sex": ("patient", "sex_standard", None),
    "source_sex": ("patient", "sex_standard", None),
}
CANONICAL_FIELDS = {
    "source_patient_id": ("patient", "source_patient_id"),
    "sex_standard": ("patient", "sex_standard"),
    "normalized_code": ("condition", "normalized_code"),
    "normalized_test_code": ("measurement", "normalized_test_code"),
    "value_standard": ("measurement", "value_standard"),
    "unit_standard": ("measurement", "unit_standard"),
    "measured_at": ("measurement", "measured_at"),
}
IDENTIFIER_TOKENS = ("name", "phone", "id_number", "address", "身份证")
MAX_CELL_BYTES = 16_384
RETRIEVAL_VERSION = "local-hybrid-retrieval@1.0.0"
TARGET_REGISTRY = (
    ("patient", "source_patient_id", "patient", "source patient identifier patient id"),
    ("patient", "sex_standard", "patient", "sex gender biological sex"),
    ("patient", "date_of_birth", "patient", "birth date dob patient"),
    ("patient", "province", "patient", "province region geography patient"),
    ("visit", "source_visit_id", "visit", "visit encounter identifier admission"),
    ("visit", "admit_at", "visit", "admission admit date encounter"),
    ("visit", "discharge_at", "visit", "discharge date encounter"),
    ("condition", "normalized_code", "condition", "diagnosis code disease condition icd"),
    ("condition", "normalized_name", "condition", "diagnosis disease condition name"),
    ("measurement", "normalized_test_code", "measurement", "laboratory lab test code"),
    ("measurement", "normalized_test_name", "measurement", "laboratory lab test name"),
    ("measurement", "value_standard", "measurement", "lab measurement result value numeric"),
    ("measurement", "unit_standard", "measurement", "lab measurement unit"),
    ("measurement", "measured_at", "measurement", "lab measurement result date"),
    ("procedure", "normalized_code", "procedure", "procedure operation code"),
    ("drug", "normalized_code", "drug", "medication drug code"),
)


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _infer_type(values: list[str]) -> str:
    if not values: return "unknown"
    if all(re.fullmatch(r"-?\d+(\.\d+)?", value.strip()) for value in values): return "decimal"
    if all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()) for value in values): return "date"
    return "string"


def _safe_summary(field: str, values: list[str]) -> dict[str, object]:
    """Return aggregate-only metadata; do not persist or expose example values."""
    if any(token in field.lower() for token in IDENTIFIER_TOKENS): return {"classification": "restricted", "non_null_count": len([v for v in values if v])}
    return {"classification": "metadata_safe", "non_null_count": len([v for v in values if v]), "distinct_count": len(set(values)), "sample_kind": _infer_type(values[:20])}


def _tokens(value: str) -> list[str]:
    """Tokenize only safe schema/registry text for local retrieval."""
    return re.findall(r"[a-z]+|[\u4e00-\u9fff]+|\d+", value.lower().replace("_", " "))


def _domain_for_field(field: str, unit: str | None) -> str | None:
    tokens = set(_tokens(field))
    if unit or tokens & {"alt", "ast", "tbil", "lab", "test", "result", "value", "unit"}:
        return "measurement"
    if tokens & {"diagnosis", "disease", "icd", "condition"}:
        return "condition"
    if tokens & {"visit", "admit", "discharge", "encounter"}:
        return "visit"
    if tokens & {"drug", "medication", "dose"}:
        return "drug"
    if tokens & {"procedure", "operation", "surgery"}:
        return "procedure"
    if tokens & {"patient", "sex", "gender", "birth", "province"}:
        return "patient"
    return None


def _hashed_vector(tokens: list[str], dimensions: int = 32) -> list[float]:
    vector = [0.0] * dimensions
    for token in tokens:
        digest = hashlib.sha256(token.encode()).digest()
        vector[digest[0] % dimensions] += 1.0 if digest[1] % 2 else -1.0
    return vector


def _cosine(left: list[float], right: list[float]) -> float:
    denominator = math.sqrt(sum(x * x for x in left)) * math.sqrt(sum(x * x for x in right))
    return sum(x * y for x, y in zip(left, right)) / denominator if denominator else 0.0


def retrieve_candidates(field: str, inferred_type: str, unit: str | None, limit: int = 5) -> list[dict[str, object]]:
    """Use local BM25 plus fixed hashed vectors; never send schema metadata over the network."""
    domain = _domain_for_field(field, unit)
    registry = [item for item in TARGET_REGISTRY if domain is None or item[2] == domain]
    query_tokens = _tokens(f"{field} {inferred_type} {unit or ''}")
    documents = [_tokens(f"{entity} {target} {description}") for entity, target, _, description in registry]
    total = len(documents) or 1
    average_length = sum(len(document) for document in documents) / total or 1.0
    query_vector = _hashed_vector(query_tokens)
    scored: list[dict[str, object]] = []
    for item, document in zip(registry, documents):
        bm25 = 0.0
        for token in set(query_tokens):
            frequency = document.count(token)
            if not frequency:
                continue
            document_frequency = sum(token in candidate for candidate in documents)
            idf = math.log(1 + (total - document_frequency + 0.5) / (document_frequency + 0.5))
            bm25 += idf * (frequency * 2.0) / (frequency + 1.0 * (1 - 0.75 + 0.75 * len(document) / average_length))
        dense = _cosine(query_vector, _hashed_vector(document))
        scored.append({"domain": item[2], "target_entity": item[0], "target_field": item[1], "bm25_score": round(bm25, 6), "dense_score": round(dense, 6), "evidence": {"retrieval_version": RETRIEVAL_VERSION, "domain_selection": domain or "all", "query_tokens": query_tokens}})
    bm25_max = max((float(item["bm25_score"]) for item in scored), default=1.0) or 1.0
    for item in scored:
        item["fusion_score"] = round(0.6 * float(item["bm25_score"]) / bm25_max + 0.4 * max(float(item["dense_score"]), 0.0), 6)
    return sorted(scored, key=lambda item: (-float(item["fusion_score"]), str(item["target_entity"]), str(item["target_field"])))[:limit]


def parse_tabular_upload(filename: str, content: bytes, max_rows: int = 1000, max_bytes: int = 10_000_000) -> tuple[str, list[str], list[list[str]]]:
    """Parse CSV/XLSX in memory, returning schema only to downstream profiling."""
    if not filename or len(content) > max_bytes:
        raise ValueError("The uploaded file exceeds the configured size limit")
    extension = filename.rsplit(".", 1)[-1].lower()
    if extension == "csv":
        rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig"))))
    elif extension in {"xlsx", "xlsm"}:
        book = load_workbook(io.BytesIO(content), read_only=True, data_only=True); sheet = book.active
        rows = [["" if value is None else str(value) for value in row] for row in sheet.iter_rows(values_only=True)]
    else: raise ValueError("Only CSV and Excel uploads are supported")
    if not rows or not rows[0]: raise ValueError("A header row is required")
    headers = [str(x).strip() for x in rows[0]]
    if any(not header for header in headers) or len(set(headers)) != len(headers):
        raise ValueError("Headers must be non-empty and unique")
    bounded_rows = [[cell[:MAX_CELL_BYTES] for cell in row] for row in rows[1 : max_rows + 1]]
    return filename.rsplit(".", 1)[0], headers, bounded_rows


def _suggestion_for_field(session: Session, field: str) -> tuple[str, tuple[str, str] | None, float, dict[str, object]]:
    """Resolve suggestions by approved history, exact canonical name, vocabulary, then alias."""
    normalized = field.strip().lower()
    historical = session.query(MappingDefinition).filter(
        MappingDefinition.source_field.ilike(field), MappingDefinition.status == "approved"
    ).order_by(MappingDefinition.confidence.desc()).first()
    if historical:
        return "historical", (historical.canonical_entity, historical.canonical_field), min(historical.confidence, 0.99), {
            "rule_version": "mapping-rules@1.1.0",
            "historical_mapping_definition_id": str(historical.mapping_definition_id),
        }
    if normalized in CANONICAL_FIELDS:
        return "exact", CANONICAL_FIELDS[normalized], 0.98, {"rule_version": "mapping-rules@1.1.0", "exact_canonical_name": normalized}
    if normalized in VOCABULARY_ALIASES:
        target = VOCABULARY_ALIASES[normalized]
        return "vocabulary", target[:2], 0.97, {"rule_version": "mapping-rules@1.1.0", "vocabulary_concept": target[2]}
    if normalized in ALIASES:
        target = ALIASES[normalized]
        return "alias", target[:2], 0.93, {"rule_version": "mapping-rules@1.1.0", "matched_alias": normalized}
    return "abstain", None, 0.0, {"rule_version": "mapping-rules@1.1.0", "reason": "no_deterministic_match"}


def create_import_job(session: Session, source_kind: str, display_name: str, headers: list[str], rows: list[list[str]], artifact_hash: str) -> dict[str, object]:
    """Profile one source schema and persist deterministic rule-based suggestions."""
    profiles = []
    for ordinal, field in enumerate(headers):
        values = [row[ordinal] for row in rows if ordinal < len(row)]
        profiles.append({"table": display_name, "field": field, "ordinal": ordinal, "type": _infer_type(values[:20]), "summary": _safe_summary(field, values)})
    job = ImportJob(source_kind=source_kind, display_name=display_name, status="completed", artifact_hash=artifact_hash, profile_hash=_hash(profiles), manifest={"profile_version": "mapping-profile@1.0.0", "source_kind": source_kind, "field_count": len(profiles), "row_limit": len(rows)})
    session.add(job); session.flush()
    for item in profiles:
        profile = SourceFieldProfile(import_job_id=job.import_job_id, table_name=item["table"], field_name=item["field"], ordinal=item["ordinal"], inferred_type=item["type"], unit="U/L" if item["field"].lower() in {"alt", "ast"} else None, safe_summary=item["summary"]); session.add(profile); session.flush()
        route, target, confidence, evidence = _suggestion_for_field(session, item["field"])
        evidence["safe_summary"] = item["summary"]
        suggestion = MappingSuggestion(import_job_id=job.import_job_id, source_field_profile_id=profile.source_field_profile_id, route=route, target_entity=target[0] if target else None, target_field=target[1] if target else None, confidence=confidence, evidence=evidence, status="review_required" if target else "unmapped")
        session.add(suggestion); session.flush()
        candidates = retrieve_candidates(item["field"], item["type"], profile.unit)
        for rank, candidate in enumerate(candidates, start=1):
            session.add(MappingCandidate(mapping_suggestion_id=suggestion.mapping_suggestion_id, rank=rank, **candidate))
        session.add(MappingImportAuditEvent(import_job_id=job.import_job_id, mapping_suggestion_id=suggestion.mapping_suggestion_id, event_type="suggested", details={"route": route, "profile_hash": job.profile_hash, "rule_version": "mapping-rules@1.1.0", "retrieval_version": RETRIEVAL_VERSION, "candidate_count": len(candidates)}))
    session.add(MappingImportAuditEvent(import_job_id=job.import_job_id, mapping_suggestion_id=None, event_type="profiled", details={"artifact_hash": artifact_hash, "profile_hash": job.profile_hash, "field_count": len(profiles)})); session.commit()
    return {"id": str(job.import_job_id), "status": job.status, "field_count": len(profiles), "suggestion_count": len(profiles)}


def profile_postgres_table(session: Session, connection_url: str, schema: str, table: str, allowed_hosts: set[str], allowed_ports: set[int], max_rows: int) -> dict[str, object]:
    """Read only a selected PostgreSQL table's bounded schema/sample for safe profiling."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
        raise ValueError("Schema and table must be identifiers")
    parsed = urlparse(connection_url)
    if parsed.scheme not in {"postgresql", "postgresql+psycopg"} or parsed.query or parsed.fragment:
        raise ValueError("A plain PostgreSQL connection URL is required")
    host = parsed.hostname
    if host not in allowed_hosts: raise ValueError("PostgreSQL host is not allowed")
    port = parsed.port or 5432
    if port not in allowed_ports: raise ValueError("PostgreSQL port is not allowed")
    engine = create_engine(connection_url, poolclass=NullPool, connect_args={"connect_timeout": 5, "options": "-c default_transaction_read_only=on -c statement_timeout=5000"})
    with engine.connect() as connection:
        columns = connection.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema=:schema AND table_name=:table ORDER BY ordinal_position"), {"schema": schema, "table": table}).scalars().all()
        if not columns: raise ValueError("Selected table does not exist")
        quoted = ", ".join(f'"{column}"' for column in columns)
        values = connection.execute(text(f'SELECT {quoted} FROM "{schema}"."{table}" LIMIT :limit'), {"limit": max_rows}).all()
    rows = [["" if value is None else str(value)[:MAX_CELL_BYTES] for value in row] for row in values]
    artifact_hash = _hash({"schema": schema, "table": table, "columns": columns, "row_count": len(rows)})
    return create_import_job(session, "postgres", f"{schema}.{table}", list(columns), rows, artifact_hash)
