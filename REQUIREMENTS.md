# MVP Requirements

## R1. Synthetic hospital sources

Create synthetic source systems that look meaningfully different.

### HIS
- patient demographics
- encounters / admissions
- department
- discharge

### EMR
- diagnoses
- simple clinical notes
- procedures
- outcomes

### LIS
- laboratory observations
- units
- reference ranges

Generate 1,000–5,000 patients by configuration.

## R2. Dirty-data fixtures

Inject realistic defects:
- duplicate patients
- missing values
- invalid ages
- discharge before admission
- inconsistent sex coding
- ALT aliases
- AST aliases
- bilirubin unit mismatch
- impossible negative measurements
- inconsistent diagnosis names/codes
- duplicate lab rows
- mixed date formats where applicable

Dirty-data generation must be deterministic from a seed.

## R3. Canonicalization

Create a canonical intermediate model before OMOP mapping.

Normalize:
- patient identity
- sex coding
- dates
- diagnosis representation
- lab names
- measurement units

## R4. Data quality

Implement at least 20 rules across:
- completeness
- validity
- consistency
- uniqueness
- referential integrity
- clinical plausibility (non-diagnostic)

Each rule needs:
- rule ID
- description
- severity
- entity/field
- version
- result
- observed metric
- threshold

## R5. Quality score

Produce a transparent score, not a black-box number.

Output:
- overall score
- dimension scores
- failed-rule count
- critical failures
- before/after comparison

## R6. OMOP-compatible mapping

At minimum support conceptual mapping into:
- PERSON
- VISIT_OCCURRENCE
- CONDITION_OCCURRENCE
- MEASUREMENT
- DRUG_EXPOSURE
- PROCEDURE_OCCURRENCE

Full vocabulary licensing/loading is not required in v0.1.

## R7. Liver cohort

Define a demonstrative liver cohort using configurable rules such as:
- liver-related diagnosis
- selected lab availability
- minimum encounter history

The cohort definition must be versioned and inspectable.

## R8. De-identification

At minimum:
- remove direct identifiers from product output
- pseudonymous patient ID
- age generalization option
- geography generalization option
- deterministic or configurable date shift per patient
- field-level policy

Keep raw and de-identified datasets physically/logically separated.

## R9. Dataset Product

Generate a machine-readable and human-readable Dataset Card containing:
- name
- version
- description
- owner
- source systems
- patient count
- record count
- time coverage
- schema
- quality score
- quality report reference
- lineage
- de-identification status
- intended uses
- prohibited uses
- created_at
- updated_at

## R10. Lineage

Represent lineage at least at dataset/job level:

HIS/LIS/EMR
→ raw tables
→ canonical tables
→ OMOP tables
→ liver cohort
→ de-identified dataset product

Store lineage as JSON or relational records and expose via API.

## R11. API

FastAPI endpoints for:
- health
- datasets
- dataset detail
- quality report
- lineage
- run pipeline
- product export metadata

## R12. Tests

Minimum:
- unit tests for transforms
- unit tests for quality rules
- unit tests for de-identification
- integration test for end-to-end pipeline
