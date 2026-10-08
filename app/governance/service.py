"""Seed the mapping contract and produce transparent persisted quality reports."""
from __future__ import annotations
from collections import Counter
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.models import (CanonicalCondition, CanonicalMeasurement, CanonicalPatient, CanonicalVisit, CanonicalizationRun, IngestionRejection,
    LineageEvent, MappingDefinition, MappingSet, QualityResult, QualityRun, RawRecord)
from app.canonical.service import LIVER_CODES, parse_date

RULES = [("CPL-001","raw","completeness","critical"),("CPL-002","raw","completeness","warning"),("CPL-003","raw","completeness","error"),("CPL-004","raw","completeness","error"),("CPL-005","raw","completeness","error"),("VAL-001","canonical","validity","error"),("VAL-002","canonical","validity","warning"),("VAL-003","canonical","validity","error"),("VAL-004","canonical","validity","error"),("VAL-005","canonical","validity","error"),("CON-001","raw","consistency","critical"),("CON-002","raw","consistency","error"),("CON-003","canonical","consistency","error"),("CON-004","canonical","consistency","error"),("UNQ-001","raw","uniqueness","error"),("UNQ-002","canonical","uniqueness","critical"),("UNQ-003","raw","uniqueness","warning"),("REF-001","canonical","referential_integrity","critical"),("REF-002","canonical","referential_integrity","critical"),("REF-003","canonical","referential_integrity","critical"),("PLS-001","canonical","clinical_plausibility","warning"),("PLS-002","canonical","clinical_plausibility","warning")]
PAIRS=(("his","patient","patient_id","patient","source_patient_id","identity"),("his","patient","sex","patient","sex_standard","sex_v1"),("his","patient","date_of_birth","patient","date_of_birth","date_v1"),("his","patient","province","patient","province","identity"),("his","patient","city","patient","city","identity"),("his","visit","visit_id","visit","source_visit_id","identity"),("his","visit","patient_id","visit","canonical_patient_id","identity"),("his","visit","admit_at","visit","admit_at","date_v1"),("his","visit","discharge_at","visit","discharge_at","date_v1"),("emr","diagnosis","diagnosis_code","condition","normalized_code","liver_condition_v1"),("emr","diagnosis","diagnosis_name","condition","normalized_name","liver_condition_v1"),("lis","lab_result","test_name","measurement","normalized_test_name","lab_alias_v1"),("lis","lab_result","test_code","measurement","normalized_test_code","lab_alias_v1"),("lis","lab_result","value","measurement","value_standard","lab_value_v1"),("lis","lab_result","unit","measurement","unit_standard","bilirubin_mgdl_to_umoll_v1"))

def seed_mapping_set(session: Session) -> MappingSet:
    """Create the deterministic initial mapping-set manifest once."""
    existing=session.scalar(select(MappingSet).where(MappingSet.scope=="liver-core", MappingSet.version=="1.0.0"))
    if existing is None:
        session.query(MappingSet).filter(MappingSet.scope=="liver-core", MappingSet.status=="active").update({"status":"retired"})
        existing=MappingSet(scope="liver-core",version="1.0.0",status="active",description="Deterministic liver canonical mappings")
        session.add(existing); session.flush()
    if not session.scalar(select(MappingDefinition.mapping_definition_id).where(MappingDefinition.mapping_set_id==existing.mapping_set_id)):
        for system, entity, field, target, target_field, rule in PAIRS:
            session.add(MappingDefinition(mapping_set_id=existing.mapping_set_id,source_system=system,source_entity=entity,source_field=field,canonical_entity=target,canonical_field=target_field,rule_key=rule,confidence=1.0,evidence={"kind":"identity","inputs":[field],"output":target_field},status="approved"))
    session.commit(); return existing

def run_quality(session: Session, canonicalization_run_id: UUID) -> dict[str, object]:
    """Persist 22 transparent rule results for an executed canonicalization run."""
    canon=session.get(CanonicalizationRun,canonicalization_run_id)
    if canon is None or canon.status!="completed": raise ValueError("Completed canonicalization run required")
    existing=session.scalar(select(QualityRun).where(QualityRun.canonicalization_run_id==canonicalization_run_id,QualityRun.status=="completed"))
    if existing: return existing.report or {"id":str(existing.quality_run_id),"status":"completed"}
    raw=session.scalars(select(RawRecord).where(RawRecord.ingestion_run_id==canon.ingestion_run_id)).all()
    rejected=session.scalars(select(IngestionRejection).where(IngestionRejection.ingestion_run_id==canon.ingestion_run_id)).all()
    patients=session.scalars(select(CanonicalPatient).where(CanonicalPatient.canonicalization_run_id==canonicalization_run_id)).all()
    measures=session.scalars(select(CanonicalMeasurement).where(CanonicalMeasurement.canonicalization_run_id==canonicalization_run_id)).all()
    visits=session.scalars(select(CanonicalVisit).where(CanonicalVisit.canonicalization_run_id==canonicalization_run_id)).all()
    conditions=session.scalars(select(CanonicalCondition).where(CanonicalCondition.canonicalization_run_id==canonicalization_run_id)).all()
    source_rows=[x.payload for x in raw]+[x.payload for x in rejected]
    entity=lambda name:[p for p in source_rows if ("lab_result_id" in p)==(name=="lab_result") and ("diagnosis_id" in p)==(name=="diagnosis") and ("visit_id" in p)==(name=="visit") and ("patient_id" in p)]
    patient_src=[p for p in source_rows if "date_of_birth" in p]
    visit_src=[p for p in source_rows if "admit_at" in p]
    diagnosis_src=[p for p in source_rows if "diagnosis_id" in p]
    lab_src=[p for p in source_rows if "lab_result_id" in p]
    patient_ids={p.canonical_patient_id for p in patients}
    failures={
      "CPL-001":sum(not p.get("patient_id") for p in patient_src), "CPL-002":sum(not p.get("name") for p in patient_src),
      "CPL-003":sum(not p.get("admit_at") for p in visit_src), "CPL-004":sum(not p.get("value") for p in lab_src), "CPL-005":sum(not p.get("unit") for p in lab_src),
      "VAL-001":sum(p.age is None or not 0<=p.age<=120 for p in patients), "VAL-002":sum(p.sex_standard=="unknown" for p in patients),
      "VAL-003":sum(not v.admit_at or not v.discharge_at for v in visits), "VAL-004":sum(m.value_standard is None for m in measures), "VAL-005":sum(not m.unit_standard for m in measures),
      "CON-001":sum((parse_date(p.get("admit_at")) is None or parse_date(p.get("discharge_at")) is None or parse_date(p.get("discharge_at")) < parse_date(p.get("admit_at"))) for p in visit_src),
      "CON-002":sum(LIVER_CODES.get(p.get("diagnosis_code")) != p.get("diagnosis_name") for p in diagnosis_src),
      "CON-003":sum(not m.normalized_test_code or m.normalized_test_code != m.normalized_test_name for m in measures),
      "CON-004":sum(m.normalized_test_code=="TBIL" and m.unit_original=="mg/dL" and (m.value_standard is None or abs((m.value_standard/(float(m.value_original or 1)))-17.1)>.01) for m in measures),
      "UNQ-001":sum(c-1 for c in Counter(p.get("patient_id") for p in patient_src).values() if c>1), "UNQ-002":sum(c-1 for c in Counter(p.source_patient_id for p in patients).values() if c>1), "UNQ-003":sum(c-1 for c in Counter(p.get("lab_result_id") for p in lab_src).values() if c>1),
      "REF-001":sum(v.canonical_patient_id not in patient_ids for v in visits), "REF-002":sum(c.canonical_patient_id not in patient_ids for c in conditions), "REF-003":sum(m.canonical_patient_id not in patient_ids for m in measures),
      "PLS-001":sum(m.normalized_test_code in {"ALT","AST"} and (m.value_standard is None or not 0<=m.value_standard<=2000) for m in measures), "PLS-002":sum(m.normalized_test_code=="TBIL" and (m.value_standard is None or not 0<=m.value_standard<=1000) for m in measures)}
    run=QualityRun(ingestion_run_id=canon.ingestion_run_id,canonicalization_run_id=canonicalization_run_id,status="completed")
    session.add(run); session.flush(); results=[]
    for rule_id,phase,dimension,severity in RULES:
        denominator=len(raw)+len(rejected) if phase=="raw" else max(len(patients),len(measures),1)
        observed={"failed_rows":failures.get(rule_id,0),"evaluated_rows":denominator,"threshold":0}
        session.add(QualityResult(quality_run_id=run.quality_run_id,rule_id=rule_id,phase=phase,dimension=dimension,severity=severity,observed=observed)); results.append({"rule_id":rule_id,"phase":phase,"dimension":dimension,"severity":severity,"observed":observed})
    dimensions={d:100.0 for d in {r[2] for r in RULES}}
    for item in results:
        if item["observed"]["failed_rows"]: dimensions[item["dimension"]]=min(dimensions[item["dimension"]],0.0)
    report={"id":str(run.quality_run_id),"status":"completed","before":{"raw_records":len(raw),"ingestion_rejections":len(rejected)},"after":{"patients":len(patients),"measurements":len(measures)},"rule_results":results,"dimension_scores":dimensions,"overall_score":sum(dimensions.values())/len(dimensions)}
    run.report=report; session.add(LineageEvent(canonicalization_run_id=canonicalization_run_id,stage="quality",inputs={"canonicalization_run_id":str(canonicalization_run_id)},outputs={"quality_run_id":str(run.quality_run_id)},versions={"rule_set":"quality-core@1.0.0"})); session.commit(); return report
