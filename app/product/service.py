"""Build CSV dataset products from synthetic cohort data without raw identifiers."""
from __future__ import annotations

import csv
import hashlib
import hmac
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (CanonicalCondition, CanonicalMeasurement, CanonicalPatient,
    CanonicalVisit, CohortMember, CohortRun, DatasetProduct, OmopMappingRun,
    PrivacyPolicy, ProductExportAttempt, QualityRun)

POLICY = {"date_mode": "exact", "age_mode": "exact", "geography_mode": "province_only"}
ALLOWLIST = ("pseudonymous_patient_id", "age", "province", "first_visit_date", "last_visit_date", "liver_condition_codes", "alt_max", "ast_max", "tbil_max")
FORBIDDEN = ("name", "id_number", "phone", "source_patient_id", "source_visit_id", "source_row_id", "date_of_birth", "city", "payload")


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def seed_privacy_policy(session: Session, key_id: str) -> PrivacyPolicy:
    """Seed the selected exact-date, province-only policy once per key scope."""
    existing = session.scalar(select(PrivacyPolicy).where(PrivacyPolicy.slug == "liver-product-policy", PrivacyPolicy.version == "1.0.0"))
    if existing: return existing
    item = PrivacyPolicy(slug="liver-product-policy", version="1.0.0", policy=POLICY, policy_hash=_hash(POLICY), key_id=key_id)
    session.add(item); session.commit(); return item


def _pseudo(secret: str, key_id: str, patient_id: UUID) -> str:
    if not secret: raise ValueError("PSEUDONYMIZATION_SECRET must be configured")
    return hmac.new(secret.encode(), f"{key_id}:{patient_id}".encode(), hashlib.sha256).hexdigest()[:24]


def _shift(value: str | None, patient_id: UUID, policy: dict[str, str]) -> str | None:
    if not value or policy["date_mode"] == "exact": return value
    offset = int(hashlib.sha256(str(patient_id).encode()).hexdigest()[:4], 16) % 61 - 30
    return (date.fromisoformat(value) + timedelta(days=offset)).isoformat()


def _age(value: int | None, policy: dict[str, str]) -> int | str | None:
    if value is None or policy["age_mode"] == "exact": return value
    return f"{value // 10 * 10}-{value // 10 * 10 + 9}"


def _check_safe(rows: list[dict[str, object]]) -> None:
    serialized = json.dumps(rows, sort_keys=True)
    if any(key not in ALLOWLIST for row in rows for key in row) or any(word in serialized.lower() for word in FORBIDDEN):
        raise ValueError("Product projection contains a prohibited field")


def build_dataset_product(session: Session, cohort_run_id: UUID, quality_run_id: UUID, secret: str, key_id: str, retry: bool = False) -> dict[str, object]:
    """Atomically build a count-safe CSV and JSON Dataset Card for one cohort."""
    cohort, quality = session.get(CohortRun, cohort_run_id), session.get(QualityRun, quality_run_id)
    if not cohort or not quality: raise LookupError("Cohort or quality run not found")
    omop = session.get(OmopMappingRun, cohort.omop_run_id)
    if not omop or cohort.status != "completed" or quality.status != "completed" or omop.canonicalization_run_id != quality.canonicalization_run_id:
        raise RuntimeError("Completed compatible cohort and quality runs required")
    policy = seed_privacy_policy(session, key_id)
    product = session.scalar(select(DatasetProduct).where(DatasetProduct.slug == "liver-cohort-product", DatasetProduct.version == "1.0.0", DatasetProduct.cohort_run_id == cohort_run_id, DatasetProduct.quality_run_id == quality_run_id, DatasetProduct.privacy_policy_id == policy.privacy_policy_id))
    if product is None:
        product = DatasetProduct(slug="liver-cohort-product", version="1.0.0", cohort_run_id=cohort_run_id, quality_run_id=quality_run_id, privacy_policy_id=policy.privacy_policy_id); session.add(product); session.flush()
    previous = session.scalars(select(ProductExportAttempt).where(ProductExportAttempt.dataset_product_id == product.dataset_product_id).order_by(ProductExportAttempt.attempt_number.desc())).first()
    if previous and previous.status == "completed": return {"id": str(product.dataset_product_id), "status": "completed", "patient_count": previous.patient_count, "csv_path": previous.csv_path}
    if previous and previous.status == "started": raise RuntimeError("Dataset product build already running")
    if previous and not retry: raise ValueError("Failed dataset product build requires retry=true")
    attempt = ProductExportAttempt(dataset_product_id=product.dataset_product_id, attempt_number=(previous.attempt_number + 1 if previous else 1), status="started"); session.add(attempt); session.flush()
    try:
        member_ids = set(session.scalars(select(CohortMember.canonical_patient_id).where(CohortMember.cohort_run_id == cohort_run_id)).all())
        run_id = omop.canonicalization_run_id
        patients = {x.canonical_patient_id: x for x in session.scalars(select(CanonicalPatient).where(CanonicalPatient.canonicalization_run_id == run_id)).all() if x.canonical_patient_id in member_ids}
        visits = session.scalars(select(CanonicalVisit).where(CanonicalVisit.canonicalization_run_id == run_id)).all()
        conditions = session.scalars(select(CanonicalCondition).where(CanonicalCondition.canonicalization_run_id == run_id)).all()
        measurements = session.scalars(select(CanonicalMeasurement).where(CanonicalMeasurement.canonicalization_run_id == run_id)).all()
        rows: list[dict[str, object]] = []
        for patient_id, patient in patients.items():
            dates = sorted(x.admit_at for x in visits if x.canonical_patient_id == patient_id and x.admit_at)
            labs = {code: [x.value_standard for x in measurements if x.canonical_patient_id == patient_id and x.normalized_test_code == code and x.value_standard is not None] for code in ("ALT", "AST", "TBIL")}
            row: dict[str, object] = {"pseudonymous_patient_id": _pseudo(secret, policy.key_id, patient_id), "age": _age(patient.age, policy.policy), "first_visit_date": _shift(dates[0] if dates else None, patient_id, policy.policy), "last_visit_date": _shift(dates[-1] if dates else None, patient_id, policy.policy), "liver_condition_codes": ";".join(sorted({x.normalized_code or "UNKNOWN" for x in conditions if x.canonical_patient_id == patient_id})), "alt_max": max(labs["ALT"], default=None), "ast_max": max(labs["AST"], default=None), "tbil_max": max(labs["TBIL"], default=None)}
            if policy.policy["geography_mode"] == "province_only": row["province"] = patient.province
            rows.append(row)
        rows.sort(key=lambda x: str(x["pseudonymous_patient_id"])); _check_safe(rows)
        export_dir = Path("exports"); export_dir.mkdir(exist_ok=True)
        prefix = f"{product.dataset_product_id}-a{attempt.attempt_number}"; csv_path, card_path = export_dir / f"{prefix}.csv", export_dir / f"{prefix}.card.json"
        temporary = csv_path.with_suffix(".csv.tmp")
        columns = [x for x in ALLOWLIST if any(x in row for row in rows)]
        with temporary.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="raise"); writer.writeheader(); writer.writerows(rows)
        os.replace(temporary, csv_path)
        report = quality.report or {}; coverage = [x for row in rows for x in (row.get("first_visit_date"), row.get("last_visit_date")) if x]
        card = {"name": product.slug, "version": product.version, "description": "Synthetic liver cohort dataset product", "owner": "Healthcare Dataset Factory", "source_systems": ["HIS", "EMR", "LIS"], "patient_count": len(rows), "record_count": len(rows), "time_coverage": {"start": min(coverage) if coverage else None, "end": max(coverage) if coverage else None}, "schema": columns, "quality_score": report.get("overall_score"), "quality_report_reference": _hash({"quality": str(quality.quality_run_id)}), "deidentification_status": "pseudonymized", "privacy_policy": {"slug": policy.slug, "version": policy.version, "hash": policy.policy_hash, "key_id": policy.key_id}, "intended_uses": ["synthetic research prototype"], "prohibited_uses": ["clinical decision-making", "re-identification"], "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat(), "lineage": {"canonicalization": _hash({"run": str(run_id)}), "omop": _hash({"run": str(omop.omop_run_id)}), "cohort": _hash({"run": str(cohort_run_id)}), "quality": _hash({"run": str(quality_run_id)})}}
        card_path.write_text(json.dumps(card, sort_keys=True, indent=2), encoding="utf-8")
        attempt.status="completed"; attempt.patient_count=len(rows); attempt.record_count=len(rows); attempt.csv_path=str(csv_path); attempt.card_path=str(card_path); attempt.csv_hash=hashlib.sha256(csv_path.read_bytes()).hexdigest(); attempt.card_hash=hashlib.sha256(card_path.read_bytes()).hexdigest(); attempt.card=card; attempt.lineage={"cohort_run": str(cohort_run_id), "omop_run": str(omop.omop_run_id), "quality_run": str(quality_run_id), "policy_hash": policy.policy_hash}; session.commit()
        return {"id": str(product.dataset_product_id), "status": "completed", "patient_count": len(rows), "csv_path": str(csv_path)}
    except Exception:
        session.rollback(); failed = session.get(ProductExportAttempt, attempt.export_attempt_id)
        if failed: failed.status="failed"; session.commit()
        raise
