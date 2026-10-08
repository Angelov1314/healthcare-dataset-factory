"""Leakage-safe local retrieval and aggregate evaluation for the supplied synthetic bundle."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import unicodedata
from collections import defaultdict
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FactoryBenchmarkCandidateSnapshot, FactoryBenchmarkProfileSnapshot, FactoryBenchmarkRun, ImportJob, SourceFieldProfile
from app.mapping.factory_registry import REGISTRY_VERSION, registry_entries, registry_fingerprint
from app.mapping.service import RETRIEVAL_VERSION, _cosine, _hashed_vector, _tokens

METRIC_POLICY_VERSION = "factory-benchmark-evaluator@1.0.0"
DECISION_THRESHOLD = 0.10
SHEETS = ("Source_Patient", "Source_Visit", "Source_Diagnosis", "Source_Lab", "Source_Medication", "Source_Procedure")


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _domain(field: str, unit: str | None) -> str | None:
    tokens = set(_tokens(field))
    if unit or tokens & {"lab", "test", "result", "value", "unit", "alt", "cr"}: return "measurement"
    if tokens & {"diag", "dx", "icd", "condition"}: return "condition"
    if tokens & {"visit", "encounter", "adm", "disch", "ward", "bed"}: return "encounter"
    if tokens & {"drug", "med", "dose", "rxnorm", "atc", "order"}: return "drug_exposure"
    if tokens & {"proc", "anesthesia", "device"}: return "procedure"
    if tokens & {"patient", "pat", "sex", "birth", "dob", "blood", "height", "weight", "bmi"}: return "patient"
    if tokens & {"source", "update", "row", "version", "hash"}: return "provenance"
    return None


def factory_candidates(field: str, inferred_type: str, unit: str | None) -> list[dict[str, object]]:
    """Retrieve only from the immutable factory registry, without rules/history/LLM."""
    selected_domain = _domain(field, unit)
    registry = [entry for entry in registry_entries() if selected_domain is None or entry["domain"] == selected_domain]
    query = _tokens(f"{field} {inferred_type} {unit or ''}")
    docs = [_tokens(f"{item['target']} {item['description']}") for item in registry]
    total = len(docs) or 1
    average = sum(len(doc) for doc in docs) / total or 1.0
    query_vector = _hashed_vector(query)
    scores = []
    for item, document in zip(registry, docs):
        bm25 = 0.0
        for token in set(query):
            frequency = document.count(token)
            if frequency:
                df = sum(token in candidate for candidate in docs)
                idf = math.log(1 + (total - df + 0.5) / (df + 0.5))
                bm25 += idf * (frequency * 2.0) / (frequency + (1 - 0.75 + 0.75 * len(document) / average))
        scores.append({"target": item["target"], "bm25_score": round(bm25, 6), "dense_score": round(_cosine(query_vector, _hashed_vector(document)), 6), "domain": item["domain"]})
    maximum = max((float(item["bm25_score"]) for item in scores), default=1.0) or 1.0
    for item in scores: item["fusion_score"] = round(0.6 * float(item["bm25_score"]) / maximum + 0.4 * max(float(item["dense_score"]), 0.0), 6)
    return sorted(scores, key=lambda item: (-float(item["fusion_score"]), str(item["target"])))[:5]


def run_factory_benchmark(session: Session, jobs: dict[str, str], bundle_path: str) -> dict[str, object]:
    """Create an immutable aggregate benchmark run for exactly the synthetic fixture sheets."""
    bundle = Path(bundle_path)
    if not bundle.is_dir(): raise ValueError("Factory benchmark bundle is not configured")
    if set(jobs) != set(SHEETS) or len(set(jobs.values())) != len(SHEETS): raise ValueError("Exactly one import job per required source sheet is required")
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    profiles: list[tuple[str, SourceFieldProfile, ImportJob]] = []
    for sheet, raw_id in jobs.items():
        job = session.get(ImportJob, UUID(raw_id))
        source_file = bundle / f"{sheet}.csv"
        if not job or job.display_name != sheet or job.artifact_hash != hashlib.sha256(source_file.read_bytes()).hexdigest(): raise ValueError("Import jobs do not match the supplied synthetic bundle")
        sheet_profiles = session.scalars(select(SourceFieldProfile).where(SourceFieldProfile.import_job_id == job.import_job_id).order_by(SourceFieldProfile.ordinal)).all()
        source_header = next(csv.reader(source_file.open(encoding="utf-8-sig")))
        if [profile.field_name for profile in sheet_profiles] != source_header: raise ValueError("Imported source schema does not match the supplied bundle")
        profiles.extend((sheet, profile, job) for profile in sheet_profiles)
    gold_rows = list(csv.DictReader((bundle / "Gold_Field_Mapping.csv").open(encoding="utf-8-sig", newline="")))
    gold = {(row["Source Sheet"], row["Source Field"]): row for row in gold_rows}
    canonical_gold = "\n".join(",".join(unicodedata.normalize("NFC", row[key]) for key in ("Source Sheet", "Source Field", "Gold Canonical Target", "Difficulty")) for row in gold_rows)
    run = FactoryBenchmarkRun(registry_version=REGISTRY_VERSION, registry_fingerprint=registry_fingerprint(), retrieval_version=RETRIEVAL_VERSION, gold_fingerprint=hashlib.sha256(canonical_gold.encode()).hexdigest(), bundle_manifest_hash=hashlib.sha256((bundle / "manifest.json").read_bytes()).hexdigest(), metric_policy_version=METRIC_POLICY_VERSION, report={})
    session.add(run); session.flush()
    aggregate = {"total":0,"mapped":0,"top1":0,"top5":0,"gold_unmapped":0,"abstain_correct":0,"review_required":0,"unmapped":0}
    by_sheet, by_difficulty = defaultdict(lambda: {"total":0,"mapped":0,"top1":0,"top5":0}), defaultdict(lambda: {"total":0,"mapped":0,"top1":0,"top5":0})
    for sheet, profile, _ in profiles:
        row = gold[(sheet, profile.field_name)]
        candidates = factory_candidates(profile.field_name, profile.inferred_type, profile.unit)
        snapshot = FactoryBenchmarkProfileSnapshot(factory_benchmark_run_id=run.factory_benchmark_run_id, source_field_profile_id=profile.source_field_profile_id, source_sheet=sheet, field_name=profile.field_name, profile_hash=_hash({"field": profile.field_name, "type": profile.inferred_type, "unit": profile.unit, "summary": profile.safe_summary}))
        session.add(snapshot); session.flush()
        for rank, candidate in enumerate(candidates, 1): session.add(FactoryBenchmarkCandidateSnapshot(factory_benchmark_profile_snapshot_id=snapshot.factory_benchmark_profile_snapshot_id, target=str(candidate["target"]), rank=rank, bm25_score=float(candidate["bm25_score"]), dense_score=float(candidate["dense_score"]), fusion_score=float(candidate["fusion_score"]), evidence={"registry_version": REGISTRY_VERSION, "registry_fingerprint": registry_fingerprint(), "retrieval_version": RETRIEVAL_VERSION, "domain": candidate["domain"]}))
        aggregate["total"] += 1; by_sheet[sheet]["total"] += 1; by_difficulty[row["Difficulty"]]["total"] += 1
        target = row["Gold Canonical Target"]
        decision = bool(candidates and float(candidates[0]["fusion_score"]) >= DECISION_THRESHOLD)
        aggregate["review_required" if decision else "unmapped"] += 1
        if target in {"", "UNMAPPED"}:
            aggregate["gold_unmapped"] += 1; aggregate["abstain_correct"] += int(not decision); continue
        aggregate["mapped"] += 1; by_sheet[sheet]["mapped"] += 1; by_difficulty[row["Difficulty"]]["mapped"] += 1
        top = [str(candidate["target"]) for candidate in candidates]
        hit1, hit5 = int(bool(top and top[0] == target)), int(target in top)
        aggregate["top1"] += hit1; aggregate["top5"] += hit5
        by_sheet[sheet]["top1"] += hit1; by_sheet[sheet]["top5"] += hit5
        by_difficulty[row["Difficulty"]]["top1"] += hit1; by_difficulty[row["Difficulty"]]["top5"] += hit5
    report = {"registry": {"version": REGISTRY_VERSION, "fingerprint": registry_fingerprint()}, "retrieval_version": RETRIEVAL_VERSION, "metric_policy_version": METRIC_POLICY_VERSION, "source_import_jobs": jobs, "counts": aggregate, "rates": {"top1": aggregate["top1"] / aggregate["mapped"], "top5": aggregate["top5"] / aggregate["mapped"], "abstention": aggregate["abstain_correct"] / aggregate["gold_unmapped"] if aggregate["gold_unmapped"] else 0.0}, "by_sheet": dict(by_sheet), "by_difficulty": dict(by_difficulty)}
    run.report = report; session.commit()
    return {"id": str(run.factory_benchmark_run_id), **report}
