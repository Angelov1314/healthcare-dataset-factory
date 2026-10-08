"""Generate intentionally imperfect, synthetic HIS/EMR/LIS source records."""

from __future__ import annotations

import random
from collections import defaultdict
from datetime import date, timedelta
from typing import Literal
from uuid import UUID, uuid5

from pydantic import BaseModel, Field

SOURCE_NAMESPACE = UUID("a1f8b124-33e5-4b1f-9122-b70bce7e54f3")


class SourceRecord(BaseModel):
    """A source row before persistence or validation."""

    source_system: Literal["his", "emr", "lis"]
    source_entity: str
    source_row_id: UUID
    payload: dict[str, str | None] = Field(default_factory=dict)


class SyntheticSnapshot(BaseModel):
    """All generated source records for one deterministic snapshot."""

    source_snapshot_id: UUID
    seed: int
    patient_count: int
    records: dict[str, list[SourceRecord]]


def generate_snapshot(seed: int, patient_count: int) -> SyntheticSnapshot:
    """Generate a repeatable source snapshot with deliberate dirty data."""

    rng = random.Random(seed)
    snapshot_id = uuid5(SOURCE_NAMESPACE, f"synthetic:{seed}:{patient_count}")
    records: dict[str, list[SourceRecord]] = defaultdict(list)
    base_date = date(2024, 1, 1)
    provinces = [("Zhejiang", "Hangzhou"), ("Jiangsu", "Nanjing"), ("Shanghai", "Shanghai")]
    diagnosis_options = [("K74.6", "Liver cirrhosis"), ("B18.1", "Chronic hepatitis B"), ("K72.9", "Hepatic failure")]
    lab_options = [
        ("ALT", "ALT", "U/L", "7", "40"),
        ("AST", "AST", "U/L", "13", "35"),
        ("TBIL", "TBIL", "µmol/L", "5", "21"),
    ]

    def add(system: Literal["his", "emr", "lis"], entity: str, payload: dict[str, str | None]) -> None:
        row_id = uuid5(snapshot_id, f"{system}:{entity}:{len(records[entity])}")
        records[entity].append(
            SourceRecord(source_system=system, source_entity=entity, source_row_id=row_id, payload=payload)
        )

    for index in range(patient_count):
        patient_id = f"P{index + 1:06d}"
        if index == 1:
            patient_id = "P000001"  # duplicate business patient ID
        dob_year = rng.randint(1945, 2005)
        dob = date(dob_year, rng.randint(1, 12), rng.randint(1, 28))
        if index == 2:
            dob_text = "2035-01-01"  # invalid age
        elif index % 19 == 0:
            dob_text = dob.strftime("%Y/%m/%d")  # mixed date format
        else:
            dob_text = dob.isoformat()
        sex = ["M", "F", "男", "女", "1", "2"][index % 6]
        add("his", "patient", {
            "patient_id": None if index == 3 else patient_id,  # rejected at ingestion
            "name": None if index == 4 else f"Synthetic Patient {index + 1}",
            "sex": sex,
            "date_of_birth": dob_text,
            "id_number": f"ID{seed % 10000:04d}{index:08d}",
            "phone": f"138{index % 10_000_000:08d}",
            "province": provinces[index % len(provinces)][0],
            "city": provinces[index % len(provinces)][1],
        })
        visit_id = f"V{index + 1:06d}"
        admit = base_date + timedelta(days=index % 365)
        discharge = admit + timedelta(days=rng.randint(1, 12))
        if index == 5:
            discharge = admit - timedelta(days=1)
        add("his", "visit", {
            "visit_id": visit_id,
            "patient_id": patient_id,
            "admit_at": admit.isoformat() if index % 23 else admit.strftime("%d-%m-%Y"),
            "discharge_at": discharge.isoformat(),
            "department": ["Hepatology", "Gastroenterology", "Infectious Diseases"][index % 3],
            "visit_type": "inpatient" if index % 2 else "outpatient",
        })
        diagnosis_code, diagnosis_name = diagnosis_options[index % len(diagnosis_options)]
        if index == 6:
            diagnosis_name = "Acute appendicitis"  # code/name inconsistency
        add("emr", "diagnosis", {
            "diagnosis_id": f"D{index + 1:06d}", "patient_id": patient_id, "visit_id": visit_id,
            "diagnosis_code": diagnosis_code, "diagnosis_name": diagnosis_name, "diagnosis_at": admit.isoformat(),
        })
        add("emr", "procedure", {
            "procedure_id": f"PR{index + 1:06d}", "patient_id": patient_id, "visit_id": visit_id,
            "procedure_code": "89.01", "procedure_name": "Abdominal ultrasound", "procedure_at": admit.isoformat(),
        })
        add("emr", "medication", {
            "medication_id": f"M{index + 1:06d}", "patient_id": patient_id, "visit_id": visit_id,
            "drug_code": "A10", "drug_name": "Entecavir", "dose": "0.5", "dose_unit": "mg",
            "start_at": admit.isoformat(), "end_at": discharge.isoformat(),
        })
        add("emr", "outcome", {
            "patient_id": patient_id, "visit_id": visit_id, "transplant_flag": "Y" if index % 47 == 0 else "N",
            "death_flag": "N", "followup_days": str(rng.randint(30, 365)),
        })
        for lab_index, (test_code, test_name, unit, low, high) in enumerate(lab_options):
            value = str(round(rng.uniform(15, 180), 1))
            lab_name = test_name
            lab_unit = unit
            if test_code == "ALT" and index % 17 == 0:
                lab_name = ["GPT", "谷丙转氨酶", "丙氨酸氨基转移酶"][index % 3]
            if test_code == "AST" and index % 21 == 0:
                lab_name = "谷草转氨酶"
            if test_code == "TBIL" and index % 13 == 0:
                lab_name, lab_unit, value = "总胆红素", "mg/dL", str(round(float(value) / 17.1, 2))
            if index == 7 and test_code == "ALT":
                value = "-12.0"
            lab_id = f"L{index + 1:06d}{lab_index}"
            lab_payload = {
                "lab_result_id": lab_id, "patient_id": patient_id, "visit_id": visit_id,
                "test_code": test_code, "test_name": lab_name, "value": value, "unit": lab_unit,
                "reference_low": low, "reference_high": high, "measured_at": admit.isoformat(),
            }
            add("lis", "lab_result", lab_payload)
            if index == 8 and test_code == "ALT":
                add("lis", "lab_result", lab_payload.copy())  # duplicate lab business row

    return SyntheticSnapshot(source_snapshot_id=snapshot_id, seed=seed, patient_count=patient_count, records=dict(records))
