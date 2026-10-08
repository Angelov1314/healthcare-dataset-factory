# Milestone 3 Healthcare Semantics Design

## Scope

This milestone implements the original acceptance scope: OMOP-compatible local
tables, deterministic canonical-to-OMOP mapping, and a versioned liver cohort.
It uses local concept IDs only and does not load a licensed OMOP vocabulary,
make clinical decisions, de-identify data, or publish a dataset product.

## OMOP-lite mapping

## Canonical prerequisites

Add nullable `source_visit_id` and `measured_at` to `canonical.measurement` and
populate them from LIS source payload; ambiguous backfills remain null and cannot
qualify a cohort visit.

Add an `omop` schema with `person`, `visit_occurrence`, `condition_occurrence`,
`measurement`, `drug_exposure`, and `procedure_occurrence` tables. Each row has
an opaque primary key, OMOP run ID, canonical/source-row foreign key, local
concept ID, source value, and nullable unknown concept convention (`0`). Local
concept IDs use namespace `HDF_LOCAL@1.0.0`. Medication and procedure map
directly from raw EMR envelopes in this milestone, retain exact source-row IDs,
and are labelled adapter mappings rather than canonical mappings.

`omop_mapping_run` pins one completed canonicalization run, its input ingestion
run, an immutable JSON mapping-manifest snapshot, SHA-256 hash, and rule version.
Its unique identity is `(canonicalization_run_id, manifest_hash, attempt_number)`.
Completed retry returns the stored attempt, started returns 409, failed plus
`retry=true` creates the next attempt, and a changed manifest begins attempt 1.

`person` is unique per `(omop_run_id, canonical_patient_id)`; event tables are
unique per `(omop_run_id, source_row_id)` and persist canonical-record lineage.
Every OMOP event maps through canonical record ID plus source row where present.
The required
catalog `HDF_LOCAL@1.0.0` maps gender male/female/unknown to 1/2/0, ALT/AST/TBIL
to 1001/1002/1003, Entecavir to 2001, and ultrasound to 3001. Medication and
procedure rows with missing/ambiguous person/visit joins are skipped with a
persisted mapping rejection; no join is invented.

## Cohort

`cohort_definition` stores immutable version, JSON condition tree, creator, and
canonicalization/OMOP input. `cohort_run` stores definition version, input run,
status, member count, and lineage; `cohort_member` stores canonical patient IDs.
The v1 evaluator supports nested `AND`/`OR`, age comparison, liver diagnosis,
valid ALT/AST/TBIL availability, and valid visit. `time_window` is persisted
and inspected but evaluates all-time in v1.

The seeded `liver-cohort@1.0.0` requires age >= 18, an allowed liver diagnosis,
one valid TBIL, one valid ALT or AST, and a valid visit. Age is measured at the
qualifying visit admission date. A valid visit has parsed admission/discharge
with discharge >= admission; a valid measurement has numeric non-negative
standard value and recognized standard unit. Measurements must link to the
qualifying visit; repeated measurements are existential, not deduplicated.
Missing/invalid values fail their condition. v1 accepts only `all_time`; any
other time window returns 422. Conditions and allowed codes are configuration
data, not hard-coded API input.

DSL nodes are `{op:"and"|"or",children:[node...]}` or predicates
`{type:"valid_visit"}`, `{type:"age_gte",value:18}`, `{type:"liver_diagnosis",codes:[...]}`, and
`{type:"measurement",code:"ALT"|"AST"|"TBIL",operator:">=",value:n}`.
Unknown operators/types, empty children, and non-all-time windows return 422.
Evaluation is over candidate `(canonical_patient_id, source_visit_id)` pairs.
Sibling predicates in an `and` share one candidate visit; `or` returns the union
of qualifying pairs. Diagnosis, valid visit, TBIL, and ALT-or-AST qualify on the same visit; age is
floor years from ISO DOB to qualifying admission and null DOB fails. Canonical
JSON is sorted-key UTF-8 SHA-256.

Definitions are append-only with parent ID and unique semantic version; duplicate
versions return 409. A cohort run pins one completed OMOP run and matching
canonicalization run, definition version, evaluator version, and condition-tree
hash, and attempt number; this tuple is unique and retries return its completed run.
Started runs return 409; failed runs require explicit retry with attempt + 1.
OMOP runs follow the same state/attempt rule. Public
cohort and lineage APIs are count-only and never expose source-row or source
patient identifiers.

## API, safety, and tests

Add endpoints to run/read OMOP mappings, create/read cohort definitions,
preview a cohort, run it, and retrieve member count/lineage. Unknown run or
definition IDs return 404; incompatible input versions return 409; malformed
condition trees/unsupported windows return 422. No endpoint, lineage payload,
error, log, or preview exposes source patient identifiers. Member summaries are
count-only; an internal endpoint may return canonical IDs only.

PostgreSQL tests verify deterministic OMOP rows, mapping manifest persistence,
missing canonical drug/procedure inputs, definition version immutability, nested
AND/OR evaluation, age-18 boundary, invalid labs, unsupported windows, duplicate
runs, mismatched inputs, privacy-safe payloads, repeatable preview counts,
cohort membership, and lineage. `make semantics` runs OMOP mapping and
the seeded cohort after `make canonicalize`; `make pipeline-all` will later be
extended only after this command is verified.
