# Milestone 2 Governance Design

## Scope and decision

Milestone 2 turns a completed raw ingestion snapshot into a versioned canonical
liver-data representation and proves its governance controls. It includes the
canonical transforms, an auditable mapping registry, 20+ executable quality
rules, reproducible quality scoring, and job-level lineage. It does not map to
OMOP, build cohorts, de-identify data, publish a product, or add a frontend.

The selected approach is one small end-to-end governance slice: mappings drive
the canonical transform, the canonical output is assessed by a persisted quality
run, and each run emits lineage. This meets the original Milestone 2 acceptance
criteria while making mapping a genuine auditable control rather than a future
placeholder.

Alternatives considered:

1. **Selected: registry-driven canonical pipeline plus quality and lineage.**
   It is slightly larger, but every required governance artifact is observable
   and internally consistent.
2. Build mapping registry and canonical transforms first, then defer quality.
   This leaves the stated Milestone 2 acceptance criteria incomplete.
3. Hard-code field conversion and add quality rules around it. This is fastest,
   but makes mappings unreviewable and conflicts with the product direction.

## Persistent model and versioning

New PostgreSQL schemas are `canonical` and `governance`; raw source data remains
immutable. A migration adds:

- `governance.mapping_set`: immutable mapping-set identity, scope, semantic
  version, status, description, and activation state. Status is exactly
  `draft`, `active`, or `retired`; only one `active` set is allowed per scope.
  `(scope, version)` is unique.
- `governance.mapping_definition`: source system/entity/field, canonical
  entity/field, rule key, confidence, evidence JSON, status, reviewer, and
  mapping-set foreign key. Definition status is exactly `proposed`, `approved`,
  or `rejected`; `(mapping_set, source_system, source_entity, source_field,
  canonical_entity, canonical_field)` is unique. Mapping sets and definitions
  are append-only after activation; a
  correction creates a new version.
- `governance.canonicalization_run`: source snapshot, input ingestion run,
  mapping set, status, timestamps, and transform summary. A completed tuple of
  `(source_snapshot, ingestion_run, mapping_set)` is idempotent.
- `canonical.patient`, `canonical.visit`, `canonical.condition`, and
  `canonical.measurement`: canonical fields from `DATA_MODEL.md`, source-row
  provenance, and canonicalization-run foreign keys. Source business IDs are
  retained only where needed for controlled linkage, never emitted by normal
  API responses.
- `governance.quality_rule`, `governance.quality_run`, and
  `governance.quality_result`: versioned rule definitions, a target phase
  (`raw` or `canonical`), observed metrics, thresholds, status, severity,
  dimension, and reproducible score snapshot.
- `governance.lineage_event`: job-level input/output identifiers, stage, code
  version, mapping/rule versions, event time, and JSON details.

`quality_run` references both the exact completed `ingestion_run` used for raw
metrics and the exact completed `canonicalization_run` used for canonical
metrics. `canonical.patient_source` is a many-to-many provenance table with
canonical patient ID, source patient row ID, and role (`selected` or
`duplicate_evidence`), so consolidation never loses a source-row reference.
Canonical visit/condition/measurement have one non-null source-row foreign key.
Every canonical table has an opaque `canonical_row_id` primary key and a
`canonicalization_run_id`. Its logical entity ID (for example,
`canonical_patient_id`) is deterministic from snapshot plus source business
identity, but unique only together with the canonicalization run. Thus a
`--new-run` creates a retained output copy with distinct row primary keys,
while `(canonicalization_run_id, logical_entity_id)` is unique for each table.
The patient provenance table references `canonical_row_id`, not only the logical
patient ID.

The initial active mapping set is `liver-core@1.0.0` in scope `liver-core`,
inserted through a repeatable seed operation. Activation validates that every
entry in the required mapping catalogue below has exactly one approved
definition; only then does it atomically retire the preceding active set. All
mappings are deterministic suggestions with
`confidence=1.0`, an explicit normalization rule key, machine-readable evidence
(aliases, source type, or conversion constant), and `approved` status. This is
not an AI mapping claim; future AI suggestions may create draft mappings in the
same registry.

Evidence is JSON with `kind`, `inputs`, `output`, and optional `constant` keys.
`kind` is one of `identity`, `sex_code_map`, `date_parse`, `code_normalization`,
`alias_normalization`, or `unit_conversion`. The required `liver-core@1.0.0`
catalogue is exactly the following individual pairs (a semicolon denotes a
separate definition for the same source field):

| Source entity.field | Canonical entity.field | Rule key |
| --- | --- | --- |
| patient.patient_id | patient.source_patient_id | identity |
| patient.sex | patient.sex_standard | sex_v1 |
| patient.date_of_birth | patient.date_of_birth | date_v1 |
| patient.province | patient.province | identity |
| patient.city | patient.city | identity |
| visit.visit_id | visit.source_visit_id | identity |
| visit.patient_id | visit.canonical_patient_id | identity |
| visit.admit_at | visit.admit_at | date_v1 |
| visit.discharge_at | visit.discharge_at | date_v1 |
| visit.department | visit.department | identity |
| visit.visit_type | visit.visit_type | identity |
| diagnosis.diagnosis_id | condition.source_diagnosis_id | identity |
| diagnosis.patient_id | condition.canonical_patient_id | identity |
| diagnosis.visit_id | condition.source_visit_id | identity |
| diagnosis.diagnosis_code | condition.source_code; condition.normalized_code | liver_condition_v1 |
| diagnosis.diagnosis_name | condition.source_name; condition.normalized_name | liver_condition_v1 |
| diagnosis.diagnosis_at | condition.diagnosis_at | date_v1 |
| lab_result.lab_result_id | measurement.source_lab_result_id | identity |
| lab_result.patient_id | measurement.canonical_patient_id | identity |
| lab_result.visit_id | measurement.source_visit_id | identity |
| lab_result.test_code | measurement.normalized_test_code | lab_alias_v1 |
| lab_result.test_name | measurement.source_test_name; measurement.normalized_test_name | lab_alias_v1 |
| lab_result.value | measurement.value_original; measurement.value_standard | identity; lab_value_v1 |
| lab_result.unit | measurement.unit_original; measurement.unit_standard | identity; bilirubin_mgdl_to_umoll_v1 |
| lab_result.measured_at | measurement.measured_at | date_v1 |

`source_visit_id`, `source_diagnosis_id`, `diagnosis_at`, and
`source_lab_result_id` are canonical-model provenance extensions, nullable only
where the source input is absent. The declared rule keys are `identity`,
`sex_v1`, `date_v1`, `liver_condition_v1`, `lab_alias_v1`, `lab_value_v1`, and
`bilirubin_mgdl_to_umoll_v1`. The immutable seeded
`liver-semantic-config@1.0.0` contains the liver code/name pairs, lab aliases,
unit constants, and date formats named in this specification; its version and
the application transform version are recorded in canonicalization lineage.
Procedure, medication, and outcome source entities are explicitly deferred until
the OMOP/semantic milestone; no canonical rows are silently produced for them.

## Canonicalization behavior

`make canonicalize` selects the latest completed ingestion run for the active
source snapshot (or accepts explicit IDs). It refuses to run with no active,
approved mapping set or no completed raw ingestion. It reads raw envelopes only,
never re-reads source-zone tables. The command returns an existing completed
run for the same snapshot/input/mapping tuple unless `--new-run` is requested.

The pipeline uses small pure transform functions:

- Patient identity: valid source patient rows are grouped by business patient
  ID. Duplicate IDs are deterministically consolidated by the lowest immutable
  source-row UUID; the remaining rows are counted as duplicate source evidence.
  Canonical IDs are deterministic UUIDs from source snapshot plus business ID.
- Sex: `M`, `男`, and `1` become `male`; `F`, `女`, and `2` become `female`.
  Unknown values become `unknown` and are preserved for quality reporting.
- Dates: ISO 8601, `YYYY/MM/DD`, and `DD-MM-YYYY` parse to date/datetime.
  Unparseable or future birth dates produce null canonical values rather than
  invented data. Age is calculated at fixed `2024-12-31`, so it is reproducible.
- Visits: only visits with a canonical patient link are emitted; their original
  timestamps and department/type are standardized but not corrected.
- Conditions: source code/name pairs normalize through the liver configuration;
  unmatched values remain as explicit `UNKNOWN` normalizations.
- Measurements: ALT, GPT, `谷丙转氨酶`, and `丙氨酸氨基转移酶` normalize to ALT;
  AST aliases normalize to AST; TBIL/`总胆红素` normalize to TBIL. TBIL mg/dL
  converts to µmol/L using `17.1`; other values retain their numeric value and
  unit. Non-numeric or impossible values are retained as null standard values,
  with the original value/unit retained for quality assessment.

Unexpected persistence failures roll back the current canonical entity batch,
mark the canonicalization run failed, and preserve all raw data and prior
completed canonical runs. Transform-level rejects and link omissions are
included in the run summary without logging direct identifiers.

## Quality engine and score

`make quality` evaluates an explicit canonicalization run and its recorded input
ingestion run. It seeds exactly the following 22 versioned, non-diagnostic
rules and stores every result; no rule is derived from an opaque score. `R` and
`C` denote raw and canonical phase applicability, respectively. Every rule
uses `failed_rows / evaluated_rows` as its metric and has a maximum failure
threshold of zero unless shown otherwise.

| ID | Phase | Dimension | Evaluator / entity-field | Severity | Threshold |
| --- | --- | --- | --- | --- | --- |
| CPL-001 | R | completeness | patient.patient_id present | critical | 0 |
| CPL-002 | R | completeness | patient.name present | warning | 0 |
| CPL-003 | R | completeness | visit.admit_at present | error | 0 |
| CPL-004 | R | completeness | lab_result.value present | error | 0 |
| CPL-005 | R | completeness | lab_result.unit present | error | 0 |
| VAL-001 | C | validity | patient.age in 0..120 | error | 0 |
| VAL-002 | C | validity | patient.sex_standard in male/female | warning | 0 |
| VAL-003 | C | validity | visit admit/discharge parsed | error | 0 |
| VAL-004 | C | validity | measurement.value_standard numeric | error | 0 |
| VAL-005 | C | validity | measurement.unit_standard recognized | error | 0 |
| CON-001 | R | consistency | parsed discharge_at >= admit_at | critical | 0 |
| CON-002 | R | consistency | diagnosis code/name in liver configuration | error | 0 |
| CON-003 | C | consistency | measurement normalized code/name agree | error | 0 |
| CON-004 | C | consistency | TBIL mg/dL conversion ratio = 17.1 ± 0.01 | error | 0 |
| UNQ-001 | R | uniqueness | patient.patient_id has one source row | error | 0 |
| UNQ-002 | C | uniqueness | patient.source_patient_id unique | critical | 0 |
| UNQ-003 | R | uniqueness | lab_result.lab_result_id has one source row | warning | 0 |
| REF-001 | C | referential integrity | visit canonical_patient exists | critical | 0 |
| REF-002 | C | referential integrity | condition patient and visit exist | critical | 0 |
| REF-003 | C | referential integrity | measurement patient and visit exist | critical | 0 |
| PLS-001 | C | clinical plausibility | ALT/AST value_standard in 0..2000 U/L | warning | 0 |
| PLS-002 | C | clinical plausibility | TBIL value_standard in 0..1000 µmol/L | warning | 0 |

`CON-002` treats a code/name pair absent from the external liver configuration
as a failure; it makes no diagnosis. `CON-004` evaluates only source TBIL rows
whose original unit is mg/dL. The exact rule identifiers, evaluator keys,
thresholds, and versions are seeded as `quality-core@1.0.0`.

Each rule has an ID, description, entity/field, version, severity, threshold,
SQL/Python evaluator key, result status, observed metric, numerator,
denominator, and details JSON. A quality run first evaluates its specified raw
ingestion run (`before`) then its specified canonicalization run (`after`);
both phase results are persisted under one report identity. The report always
discloses source rows, raw envelopes, ingestion rejections, canonical record
counts, and omissions by entity. Every raw-phase evaluator consumes the union
of `raw.record` payloads and `raw.ingestion_rejection` payloads for the selected
ingestion run; rejection payloads count toward both numerator and denominator.
Consequently CPL-001 observes the intentionally rejected missing patient ID.
It never presents different raw/canonical populations as a quality improvement
claim; before/after metrics are an auditable transform comparison.

For the canonical report, dimension score = `100 × (1 - weighted failures /
weighted evaluated rows)` clamped to 0–100, where severity weights are info=0,
warning=1, error=3, and critical=5. A raw-phase dimension has the same formula;
dimensions without applicable raw rules are `not_applicable`, not zero. Overall
score is the equally weighted mean of applicable dimension scores. The quality
run stores the complete result snapshot, so re-reading the report always
returns the original scores. Rerunning with the same ingestion,
canonicalization, and rule-set version returns the prior completed quality run
unless explicitly requested.

## Lineage, API, and commands

Every completed canonicalization writes a lineage event from its raw ingestion
run/source snapshot to canonical table record counts, including mapping-set and
transform version. Every completed quality run writes an event from the
canonicalization run to its quality report, including rule-set version and
scores. This is job/dataset-level lineage, not yet field-level lineage.

New API contracts are Pydantic models. `GET /mapping-sets?scope=liver-core`
returns `{items:[{id,scope,version,status}]}`; `GET /mapping-sets/{id}/definitions`
returns definitions including evidence. `POST /runs/canonicalization` accepts
optional `{ingestion_run_id,mapping_set_id,new_run}` and returns
`{id,status,summary}`; missing referenced IDs return 404 and invalid run state
returns 409. `GET /runs/canonicalization/{id}` returns the same summary.
`POST /runs/quality` accepts `{canonicalization_run_id,new_run}` and returns
`{id,status,overall_score,dimension_scores}`; it uses 404/409 equivalently.
`GET /quality-reports/{quality_run_id}` returns `before`, `after`, population
and omission disclosures, rule results, and scores. `GET
/lineage/canonicalization-runs/{id}` returns `{items:[{id,stage,inputs,outputs,
versions,occurred_at}]}`. Mutating mapping-review endpoints are deferred until
the Human Review milestone.

Developer commands are:

```bash
make canonicalize
make quality
make pipeline-all
```

`pipeline-all` runs seed, raw ingestion, canonicalization, and quality in order.
The README documents the commands and how to inspect their JSON summaries.

## Testing and acceptance evidence

Mandatory PostgreSQL integration tests cover: deterministic canonical transforms
and aliases/unit conversion; duplicate-patient consolidation; idempotent runs;
mapping version activation and persistence; 22 seeded rules; persisted
before/after results; score reproducibility; and canonicalization/quality
lineage. Unit tests cover every pure normalizer and score calculation. API tests
verify contract shape and database readiness.

Milestone 2 passes only when `make pipeline-all` completes using the 1,000–5,000
patient synthetic fixture, the report contains at least 20 executed rules with
persisted before/after metrics and six dimension scores, and lineage is
retrievable for the executed pipeline.

## Assumptions and deferred work

- The initial mapping set is deterministic rules, not a machine-learning or LLM
  feature. Its evidence/confidence fields establish the review-ready contract.
- Duplicate source patients are consolidated only for canonical production;
  their raw records and quality evidence remain intact.
- This milestone does not repair source facts or make clinical conclusions.
- OMOP tables, human approval/edit/reject flows, cohort criteria, privacy,
  dataset packaging, RBAC, and field-level lineage remain separate milestones.
