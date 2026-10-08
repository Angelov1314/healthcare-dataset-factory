"""Registry-backed deterministic canonicalization."""
from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID, uuid4, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (CanonicalCondition, CanonicalMeasurement, CanonicalPatient, CanonicalVisit,
    CanonicalizationRun, FieldLineage, IngestionRun, LineageEvent, MappingDefinition, MappingSet, RawRecord)

NAMESPACE = UUID("a7f6eada-450b-497e-a1d1-5684b2c04576")
LIVER_CODES = {"K74.6": "Liver cirrhosis", "B18.1": "Chronic hepatitis B", "K72.9": "Hepatic failure"}
ALIASES = {"ALT": "ALT", "GPT": "ALT", "谷丙转氨酶": "ALT", "丙氨酸氨基转移酶": "ALT", "AST": "AST", "谷草转氨酶": "AST", "TBIL": "TBIL", "总胆红素": "TBIL"}

def parse_date(value: str | None) -> date | None:
    """Parse source date formats without inventing invalid values."""
    if not value:
        return None
    for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y"):
        try: return datetime.strptime(value, pattern).date()
        except ValueError: pass
    return None

def normalize_sex(value: str | None) -> str:
    """Normalize known source sex codes."""
    return {"M": "male", "男": "male", "1": "male", "F": "female", "女": "female", "2": "female"}.get(value or "", "unknown")

def date_text(value: str | None) -> str | None:
    """Return a normalized ISO date when parsing succeeds."""
    parsed = parse_date(value)
    return parsed.isoformat() if parsed else None

def active_mapping_set(session: Session) -> MappingSet:
    """Return the active liver mapping set."""
    mapping = session.scalar(select(MappingSet).where(MappingSet.scope == "liver-core", MappingSet.status == "active"))
    if mapping is None: raise ValueError("No active liver-core mapping set")
    return mapping

def mapping_reader(session: Session, mapping_set_id: UUID):
    """Build a read-only source-field resolver from approved registry definitions."""
    definitions=session.scalars(select(MappingDefinition).where(MappingDefinition.mapping_set_id==mapping_set_id, MappingDefinition.status=="approved")).all()
    index={(d.source_entity,d.canonical_entity,d.canonical_field):d.source_field for d in definitions}
    def read(entity: str, target_entity: str, target_field: str, payload: dict[str, str | None]) -> str | None:
        source=index.get((entity,target_entity,target_field))
        return payload.get(source) if source else None
    return read

def canonicalize(session: Session, ingestion_run_id: UUID, mapping_set_id: UUID | None = None) -> dict[str, object]:
    """Transform one completed raw ingestion run into canonical rows."""
    ingestion = session.get(IngestionRun, ingestion_run_id)
    if ingestion is None or ingestion.status != "completed": raise ValueError("Completed ingestion run required")
    mapping = session.get(MappingSet, mapping_set_id) if mapping_set_id else active_mapping_set(session)
    if mapping is None or mapping.status != "active": raise ValueError("Active mapping set required")
    existing = session.scalar(select(CanonicalizationRun).where(CanonicalizationRun.ingestion_run_id == ingestion_run_id, CanonicalizationRun.mapping_set_id == mapping.mapping_set_id))
    if existing and existing.status == "completed": return existing.summary or {"id": str(existing.canonicalization_run_id), "status": "completed"}
    run = CanonicalizationRun(source_snapshot_id=ingestion.source_snapshot_id, ingestion_run_id=ingestion_run_id, mapping_set_id=mapping.mapping_set_id, status="started")
    session.add(run); session.flush()
    rows = session.scalars(select(RawRecord).where(RawRecord.ingestion_run_id == ingestion_run_id)).all()
    grouped: dict[str, list[RawRecord]] = {}
    for row in rows: grouped.setdefault(row.source_entity, []).append(row)
    read=mapping_reader(session, mapping.mapping_set_id)
    patients: dict[str, UUID] = {}
    for row in grouped.get("patient", []):
        p = row.payload; source_id = read("patient","patient","source_patient_id",p)
        if not source_id or source_id in patients: continue
        logical = uuid5(NAMESPACE, f"{ingestion.source_snapshot_id}:patient:{source_id}"); patients[source_id] = logical
        dob = parse_date(read("patient","patient","date_of_birth",p)); age = 2024 - dob.year - ((12,31) < (dob.month,dob.day)) if dob and dob <= date(2024,12,31) else None
        patient_row=CanonicalPatient(canonicalization_run_id=run.canonicalization_run_id, canonical_patient_id=logical, source_patient_id=source_id, sex_standard=normalize_sex(read("patient","patient","sex_standard",p)), date_of_birth=dob.isoformat() if dob else None, age=age, province=read("patient","patient","province",p), city=read("patient","patient","city",p))
        session.add(patient_row); session.flush()
        for field,source_field in (("source_patient_id","patient_id"),("sex_standard","sex"),("date_of_birth","date_of_birth")):
            session.add(FieldLineage(canonicalization_run_id=run.canonicalization_run_id,canonical_record_id=patient_row.canonical_row_id,canonical_entity="patient",canonical_field=field,source_row_id=row.source_row_id,source_entity="patient",source_field=source_field,mapping_definition_id=None,transform_version="liver-semantic-config@1.0.0"))
    for row in grouped.get("visit", []):
        p=row.payload; patient=patients.get(read("visit","visit","canonical_patient_id",p) or p.get("patient_id") or "")
        if patient: session.add(CanonicalVisit(canonicalization_run_id=run.canonicalization_run_id, source_row_id=row.source_row_id, source_visit_id=p.get("visit_id") or "", canonical_patient_id=patient, admit_at=date_text(p.get("admit_at")), discharge_at=date_text(p.get("discharge_at")), department=p.get("department"), visit_type=p.get("visit_type")))
    for row in grouped.get("diagnosis", []):
        p=row.payload; patient=patients.get(p.get("patient_id") or ""); code=p.get("diagnosis_code")
        if patient: session.add(CanonicalCondition(canonicalization_run_id=run.canonicalization_run_id, source_row_id=row.source_row_id, canonical_patient_id=patient, source_visit_id=p.get("visit_id"), source_code=code, source_name=p.get("diagnosis_name"), normalized_code=code if code in LIVER_CODES else "UNKNOWN", normalized_name=LIVER_CODES.get(code, "UNKNOWN")))
    for row in grouped.get("lab_result", []):
        p=row.payload; patient=patients.get(read("lab_result","measurement","canonical_patient_id",p) or p.get("patient_id") or ""); test=ALIASES.get(read("lab_result","measurement","normalized_test_name",p) or p.get("test_name") or p.get("test_code") or "")
        if not patient: continue
        try: value=float(p.get("value") or "")
        except ValueError: value=None
        unit=p.get("unit"); standard=value * 17.1 if test == "TBIL" and unit == "mg/dL" and value is not None else value
        standard_unit="µmol/L" if test == "TBIL" else unit
        measurement=CanonicalMeasurement(canonicalization_run_id=run.canonicalization_run_id, canonical_patient_id=patient, source_row_id=row.source_row_id, source_visit_id=p.get("visit_id"), measured_at=date_text(p.get("measured_at")), normalized_test_code=test, normalized_test_name=test, value_original=p.get("value"), unit_original=unit, value_standard=standard, unit_standard=standard_unit)
        session.add(measurement); session.flush()
        for field,source_field in (("normalized_test_name","test_name"),("value_standard","value"),("unit_standard","unit")):
            session.add(FieldLineage(canonicalization_run_id=run.canonicalization_run_id,canonical_record_id=measurement.canonical_row_id,canonical_entity="measurement",canonical_field=field,source_row_id=row.source_row_id,source_entity="lab_result",source_field=source_field,mapping_definition_id=None,transform_version="liver-semantic-config@1.0.0"))
    summary={"id":str(run.canonicalization_run_id),"status":"completed","patients":len(patients),"raw_records":len(rows)}
    run.status="completed"; run.summary=summary; run.completed_at=datetime.now(timezone.utc)
    session.add(LineageEvent(canonicalization_run_id=run.canonicalization_run_id, stage="canonicalization", inputs={"ingestion_run_id":str(ingestion_run_id)}, outputs=summary, versions={"mapping_set":mapping.version,"transform":"liver-semantic-config@1.0.0"}))
    session.commit(); return summary
