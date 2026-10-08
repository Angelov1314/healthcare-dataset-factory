"""Immutable target-only registry for the synthetic Factory benchmark."""
from __future__ import annotations

import hashlib
import json
import unicodedata

REGISTRY_VERSION = "factory-benchmark@1.0.0"

# Target-only descriptions are generated from canonical names; no Gold source aliases appear here.
_TARGETS = """patient.patient_id
patient.mrn
patient.name
patient.gender
patient.birth_date
patient.gov_id
patient.phone
patient.email
patient.address.province
patient.address.city
patient.address.full_text
patient.blood_type
patient.marital_status
patient.nationality
patient.height_cm
patient.weight_kg
patient.bmi
patient.deceased_flag
provenance.source_system
encounter.encounter_id
encounter.patient_id
encounter.encounter_number
encounter.start_datetime
encounter.end_datetime
encounter.type
encounter.department_code
encounter.department_name
encounter.ward
encounter.bed
encounter.attending_provider_id
encounter.admit_diagnosis_text
encounter.discharge_diagnosis_text
encounter.payer_type
encounter.status
encounter.emergency_flag
encounter.icu_flag
encounter.length_of_stay_days
provenance.source_record_timestamp
provenance.updated_at
provenance.row_version
condition.condition_id
condition.encounter_id
condition.patient_id
condition.source_code
condition.icd10_code
condition.source_name
condition.display_text
condition.type
condition.primary_flag
condition.present_on_admission
condition.recorded_date
condition.department_code
condition.provider_id
condition.coding_system
condition.code_version
condition.exclusion_flag
condition.note
measurement.measurement_id
measurement.encounter_id
measurement.patient_id
measurement.source_test_code
measurement.test_name
measurement.test_name_en
measurement.value
measurement.value_text
measurement.unit
measurement.reference_low
measurement.reference_high
measurement.abnormal_flag
measurement.specimen_type
measurement.specimen_collected_at
measurement.observed_at
measurement.recorded_at
measurement.reported_at
measurement.creatinine_value
measurement.alt_value
measurement.status
measurement.instrument_id
measurement.performing_department
measurement.operator_id
provenance.row_hash
measurement.comment
drug_exposure.order_id
drug_exposure.encounter_id
drug_exposure.patient_id
drug_exposure.source_drug_code
drug_exposure.local_code
drug_exposure.drug_name
drug_exposure.generic_name
drug_exposure.dose_text
drug_exposure.dose_value
drug_exposure.dose_unit
drug_exposure.route
drug_exposure.frequency
drug_exposure.start_datetime
drug_exposure.end_datetime
drug_exposure.status
drug_exposure.prn_flag
drug_exposure.prescriber_id
drug_exposure.pharmacy_status
drug_exposure.rxnorm_concept
drug_exposure.atc_code
drug_exposure.note
procedure.procedure_id
procedure.encounter_id
procedure.patient_id
procedure.source_code
procedure.name
procedure.coding_system
procedure.datetime
procedure.operator_provider_id
procedure.anesthesia_type
procedure.body_site
procedure.status
procedure.device_flag
procedure.note""".splitlines()


def _domain(entity: str) -> str:
    return "patient" if entity.startswith("patient") else entity


def registry_entries() -> list[dict[str, str]]:
    """Return the canonically ordered target-only benchmark registry."""
    return [
        {"target": target, "target_entity": target.rsplit(".", 1)[0], "target_field": target.rsplit(".", 1)[1], "domain": _domain(target.rsplit(".", 1)[0]), "description": target.replace(".", " ").replace("_", " ")}
        for target in sorted(unicodedata.normalize("NFC", target) for target in _TARGETS)
    ]


def registry_fingerprint() -> str:
    """Return the stable NFC/sorted-key fingerprint of the target artifact."""
    payload = json.dumps(registry_entries(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
