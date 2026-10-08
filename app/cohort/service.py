"""A deliberately small, versioned liver-cohort evaluator."""
from __future__ import annotations

import hashlib
import json
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (CanonicalPatient, CohortDefinition, CohortMember, CohortRun,
    OmopConditionOccurrence, OmopMappingRun, OmopMeasurement, OmopVisitOccurrence)

EVALUATOR_VERSION = "1.0.0"
LIVER_TREE = {
    "op": "and", "children": [
        {"type": "valid_visit"}, {"type": "age_gte", "value": 18},
        {"type": "liver_diagnosis", "codes": [1101, 1102, 1103]},
        {"type": "measurement", "code": "TBIL", "operator": ">=", "value": 0},
        {"op": "or", "children": [
            {"type": "measurement", "code": "ALT", "operator": ">=", "value": 0},
            {"type": "measurement", "code": "AST", "operator": ">=", "value": 0},
        ]},
    ],
}
CODE_TO_CONCEPT = {"ALT": 1001, "AST": 1002, "TBIL": 1003}


def canonical_hash(value: dict[str, object]) -> str:
    """Hash canonical JSON to establish a portable definition identity."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def validate_tree(node: dict[str, object]) -> None:
    """Reject unsupported conditions before an immutable definition is stored."""
    if "op" in node:
        if node.get("op") not in {"and", "or"} or not isinstance(node.get("children"), list) or not node["children"]:
            raise ValueError("Invalid boolean cohort node")
        for child in node["children"]:
            if not isinstance(child, dict): raise ValueError("Invalid cohort child")
            validate_tree(child)
        return
    kind = node.get("type")
    if kind == "valid_visit": return
    if kind == "age_gte" and isinstance(node.get("value"), int): return
    if kind == "liver_diagnosis" and isinstance(node.get("codes"), list) and node["codes"]: return
    if kind == "measurement" and node.get("code") in CODE_TO_CONCEPT and node.get("operator") in {">=", ">", "<=", "<", "="} and isinstance(node.get("value"), (int, float)): return
    raise ValueError("Unsupported cohort predicate")


def seed_liver_definition(session: Session) -> CohortDefinition:
    """Create the append-only seed definition once."""
    current = session.scalar(select(CohortDefinition).where(CohortDefinition.slug == "liver-cohort", CohortDefinition.version == "1.0.0"))
    if current: return current
    definition = CohortDefinition(slug="liver-cohort", version="1.0.0", condition_tree=LIVER_TREE,
        condition_tree_hash=canonical_hash(LIVER_TREE), time_window="all_time", creator="system", evaluator_version=EVALUATOR_VERSION)
    session.add(definition); session.commit(); return definition


def create_definition(session: Session, slug: str, version: str, condition_tree: dict[str, object], creator: str, time_window: str = "all_time", parent_definition_id: UUID | None = None) -> CohortDefinition:
    """Persist a new immutable semantic version after validation."""
    if time_window != "all_time": raise ValueError("Only all_time is supported by evaluator v1")
    validate_tree(condition_tree)
    if session.scalar(select(CohortDefinition).where(CohortDefinition.slug == slug, CohortDefinition.version == version)):
        raise RuntimeError("Cohort definition version already exists")
    item = CohortDefinition(slug=slug, version=version, condition_tree=condition_tree, condition_tree_hash=canonical_hash(condition_tree), time_window=time_window, creator=creator, parent_definition_id=parent_definition_id, evaluator_version=EVALUATOR_VERSION)
    session.add(item); session.commit(); return item


def _age_at(dob: str | None, event_date: str | None) -> int | None:
    try:
        born, at = date.fromisoformat(dob or ""), date.fromisoformat(event_date or "")
    except ValueError:
        return None
    return at.year - born.year - ((at.month, at.day) < (born.month, born.day))


def _compare(actual: float, operator: str, expected: float) -> bool:
    return {">=": actual >= expected, ">": actual > expected, "<=": actual <= expected, "<": actual < expected, "=": actual == expected}[operator]


def _evaluate(node: dict[str, object], patient: CanonicalPatient, visit: OmopVisitOccurrence,
              diagnoses: list[OmopConditionOccurrence], measurements: list[OmopMeasurement]) -> bool:
    if "op" in node:
        checks = [_evaluate(x, patient, visit, diagnoses, measurements) for x in node["children"]]  # type: ignore[index]
        return all(checks) if node["op"] == "and" else any(checks)
    kind = node["type"]
    if kind == "valid_visit":
        try: return bool(visit.visit_start_date and visit.visit_end_date and date.fromisoformat(visit.visit_end_date) >= date.fromisoformat(visit.visit_start_date))
        except ValueError: return False
    if kind == "age_gte":
        age = _age_at(patient.date_of_birth, visit.visit_start_date)
        return age is not None and age >= node["value"]  # type: ignore[operator]
    if kind == "liver_diagnosis":
        return any(d.source_visit_id == visit.source_visit_id and d.condition_concept_id in node["codes"] for d in diagnoses)  # type: ignore[operator]
    if kind == "measurement":
        concept = CODE_TO_CONCEPT[node["code"]]  # type: ignore[index]
        return any(m.source_visit_id == visit.source_visit_id and m.measurement_concept_id == concept and m.value_as_number is not None and m.value_as_number >= 0 and _compare(m.value_as_number, node["operator"], node["value"]) for m in measurements)  # type: ignore[index]
    return False


def preview_cohort(session: Session, definition_id: UUID, omop_run_id: UUID) -> set[UUID]:
    """Evaluate eligible patients, returning only opaque canonical IDs internally."""
    definition, omop_run = session.get(CohortDefinition, definition_id), session.get(OmopMappingRun, omop_run_id)
    if definition is None or omop_run is None: raise LookupError("Definition or OMOP run not found")
    if definition.time_window != "all_time": raise ValueError("Only all_time is supported by evaluator v1")
    if omop_run.status != "completed": raise RuntimeError("Completed OMOP run required")
    patients = {p.canonical_patient_id: p for p in session.scalars(select(CanonicalPatient).where(CanonicalPatient.canonicalization_run_id == omop_run.canonicalization_run_id)).all()}
    visits = session.scalars(select(OmopVisitOccurrence).where(OmopVisitOccurrence.omop_run_id == omop_run_id)).all()
    diagnoses = session.scalars(select(OmopConditionOccurrence).where(OmopConditionOccurrence.omop_run_id == omop_run_id)).all()
    measurements = session.scalars(select(OmopMeasurement).where(OmopMeasurement.omop_run_id == omop_run_id)).all()
    eligible: set[UUID] = set()
    for visit in visits:
        patient = patients.get(visit.canonical_patient_id)
        if patient and _evaluate(definition.condition_tree, patient, visit, diagnoses, measurements): eligible.add(patient.canonical_patient_id)
    return eligible


def run_cohort(session: Session, definition_id: UUID, omop_run_id: UUID, retry: bool = False) -> dict[str, object]:
    """Persist one privacy-safe cohort run and its opaque member identities."""
    previous = session.scalars(select(CohortRun).where(CohortRun.cohort_definition_id == definition_id, CohortRun.omop_run_id == omop_run_id).order_by(CohortRun.attempt_number.desc())).first()
    if previous and previous.status == "completed": return {"id": str(previous.cohort_run_id), "status": "completed", "member_count": previous.member_count}
    if previous and previous.status == "started": raise RuntimeError("Cohort run already running")
    if previous and not retry: raise ValueError("Failed cohort run requires retry=true")
    run = CohortRun(cohort_definition_id=definition_id, omop_run_id=omop_run_id, attempt_number=(previous.attempt_number + 1 if previous else 1), status="started")
    session.add(run); session.flush()
    member_ids = preview_cohort(session, definition_id, omop_run_id)
    for patient_id in member_ids: session.add(CohortMember(cohort_run_id=run.cohort_run_id, canonical_patient_id=patient_id))
    run.status="completed"; run.member_count=len(member_ids); run.lineage={"definition_id": str(definition_id), "omop_run_id": str(omop_run_id), "evaluator_version": EVALUATOR_VERSION}
    session.commit()
    return {"id": str(run.cohort_run_id), "status": "completed", "member_count": len(member_ids)}
