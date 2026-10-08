# Acceptance Criteria

## Milestone 1 — Foundation
PASS when:
- `docker compose up -d` starts PostgreSQL and API;
- migrations complete;
- deterministic synthetic hospital data can be generated;
- at least HIS/EMR/LIS source schemas exist;
- dirty-data injection is visible and testable;
- ingestion loads data into raw storage;
- automated tests pass;
- README contains exact startup commands.

## Milestone 2 — Governance
PASS when:
- canonicalization pipeline runs end to end;
- 20+ quality rules execute;
- before/after metrics are persisted;
- overall + dimension quality scores are reproducible;
- lineage records exist for pipeline steps.

## Milestone 3 — Healthcare semantics
PASS when:
- core canonical records map to OMOP-compatible tables;
- mapping documentation exists;
- liver cohort is produced from configurable criteria;
- cohort definition is versioned.

## Milestone 4 — Privacy & productization
PASS when:
- direct identifiers do not appear in product output;
- pseudonymous IDs are generated;
- age/geography/date policies are configurable;
- Dataset Card is generated;
- quality, schema, lineage, and usage policy are accessible for the product;
- product export contains no raw identifiers.

## Milestone 5 — Demo
PASS when a reviewer can:
1. seed dirty hospital data;
2. run pipeline;
3. see quality issues;
4. see normalized output;
5. build liver cohort;
6. de-identify it;
7. open dataset card;
8. inspect lineage;
9. export product metadata;
all without editing source code.
