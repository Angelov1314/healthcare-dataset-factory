# Data Model

## Synthetic source model

### HIS.Patient
- patient_id
- name
- sex
- date_of_birth
- id_number
- phone
- province
- city

### HIS.Visit
- visit_id
- patient_id
- admit_at
- discharge_at
- department
- visit_type

### EMR.Diagnosis
- diagnosis_id
- patient_id
- visit_id
- diagnosis_code
- diagnosis_name
- diagnosis_at

### EMR.Procedure
- procedure_id
- patient_id
- visit_id
- procedure_code
- procedure_name
- procedure_at

### EMR.Medication
- medication_id
- patient_id
- visit_id
- drug_code
- drug_name
- dose
- dose_unit
- start_at
- end_at

### EMR.Outcome
- patient_id
- visit_id
- transplant_flag
- death_flag
- followup_days

### LIS.LabResult
- lab_result_id
- patient_id
- visit_id
- test_code
- test_name
- value
- unit
- reference_low
- reference_high
- measured_at

## Canonical model

### canonical_patient
- canonical_patient_id
- source_patient_id
- sex_standard
- date_of_birth
- age
- province
- city

### canonical_visit
- visit_id
- canonical_patient_id
- admit_at
- discharge_at
- department
- visit_type

### canonical_condition
- condition_id
- canonical_patient_id
- visit_id
- source_code
- source_name
- normalized_code
- normalized_name

### canonical_measurement
- measurement_id
- canonical_patient_id
- visit_id
- source_test_name
- normalized_test_code
- normalized_test_name
- value_original
- unit_original
- value_standard
- unit_standard
- measured_at

## Demonstrative lab normalization

Normalize aliases:
- ALT
- GPT
- 谷丙转氨酶
- 丙氨酸氨基转移酶
→ ALT

Normalize:
- AST aliases → AST
- TBIL / 总胆红素 aliases → TBIL

Example unit conversion:
- bilirubin mg/dL → µmol/L using a documented conversion constant.

## OMOP target mapping

- canonical_patient → PERSON
- canonical_visit → VISIT_OCCURRENCE
- canonical_condition → CONDITION_OCCURRENCE
- canonical_measurement → MEASUREMENT
- medication → DRUG_EXPOSURE
- procedure → PROCEDURE_OCCURRENCE

The MVP may use local concept IDs until a proper OMOP vocabulary service is introduced.

## Liver cohort v1

Example definition:
- at least one configured liver-related diagnosis;
- at least one valid bilirubin measurement;
- at least one valid ALT or AST measurement;
- valid age;
- valid visit.

Keep diagnosis-code configuration external to code where possible.

## Product model

### dataset_product
- product_id
- slug
- name
- version
- description
- owner
- cohort_definition_id
- source_snapshot
- schema_snapshot
- quality_report_id
- lineage_root_id
- privacy_policy_id
- intended_use
- prohibited_use
- patient_count
- record_count
- status
- created_at
