# Milestone 1 Foundation Design

## Scope and decisions

This milestone establishes an observable, deterministic path from synthetic
HIS, EMR, and LIS data into isolated raw-zone PostgreSQL tables. It does not
canonicalize data, map to OMOP, run the full quality engine, build cohorts,
de-identify records, or create a product pack.

Three implementation approaches were considered:

1. Use PostgreSQL schemas and SQLAlchemy models for every source and raw table.
   This preserves source-system distinctions, makes ingestion directly
   inspectable, and prepares a clear boundary for later zones. **Selected.**
2. Store generated records only as CSV files and load them later. This is
   simpler initially but weakens reproducibility and database migration
   coverage.
3. Flatten all source records into a generic JSON event table. This is flexible
   but obscures source semantics and makes validation and later mapping harder.

## Architecture

The repository will use Python 3.11+, FastAPI, PostgreSQL, SQLAlchemy 2,
Alembic, Pydantic, and pytest. Docker Compose starts a PostgreSQL service and
the API. The API exposes a health endpoint only in this milestone; it is a
smoke-testable skeleton rather than an application UI.

Modules have one responsibility:

- `app/db`: configuration, database session, ORM models, and migrations.
- `app/synthetic`: typed source-record contracts and deterministic generation
  of HIS, EMR, and LIS records.
- `app/ingestion`: validation, run lifecycle, rejection capture, and idempotent
  source-to-raw loading.
- `app/api`: FastAPI application and health route.
- `tests`: deterministic unit tests and database-backed ingestion coverage.

Storage is separated with PostgreSQL schemas: `his_src`, `emr_src`, `lis_src`,
and `raw`. Source tables are named `his_src.patient`, `his_src.visit`,
`emr_src.diagnosis`, `emr_src.procedure`, `emr_src.medication`,
`emr_src.outcome`, and `lis_src.lab_result`. Each row has an immutable,
globally unique UUID `source_row_id` primary key and a `source_snapshot_id`
foreign key; business identifiers such as
`patient_id`, `visit_id`, and `lab_result_id` deliberately have non-unique
indexes, so injected duplicates remain visible.

Source columns retain their native names but all source values that can be dirty
are stored as `TEXT` (with the original source payload retained as JSONB). This
allows invalid ages, mixed date formats, blank required values, aliases, and
invalid measurements to be persisted faithfully. A source row is never
overwritten by the pipeline.

`raw.source_snapshot` records a UUID, generator configuration/seed, status, and
creation time. Its only statuses are `active` and `inactive`; a partial unique
index permits one active synthetic snapshot. `raw.record` preserves the source system, source entity,
immutable `source_row_id`, source payload, ingestion run, and timestamps. Its
unique key is `(source_system, source_entity, source_row_id, ingestion_run_id)`,
allowing the same source snapshot to be ingested once per run.
`raw.ingestion_rejection` stores `rejection_id`, run ID, source system/entity,
source-row ID, error code, field name, reason, payload, and timestamp.
`raw.ingestion_run` stores the run ID, snapshot ID, status (`started`,
`completed`, `failed`), started/completed timestamps, and counts. This supports
basic auditability without claiming full lineage in Milestone 1.

## Data flow and validation

`make seed` first ensures the current migration is applied, then deterministically
generates and persists a complete source snapshot to the HIS, EMR, and LIS
source tables. It generates 1,000 synthetic patients by default (configurable
from environment or CLI), including patient, visit, diagnosis, procedure,
medication, outcome, and laboratory records. It creates a `raw.source_snapshot`
manifest and writes its ID to every source row. Snapshot and source-row UUIDs
are deterministically derived from the generator configuration and seed. A
stable seed therefore upserts the same snapshot, source-row IDs, record
sequence, and deliberate defects. A different generator configuration or seed
creates a new snapshot and distinct source rows. In either case, the transaction
marks any prior active synthetic snapshot inactive and marks the selected
snapshot active; it never deletes source rows, raw envelopes, rejection records,
or completed ingestion runs. This developer fixture behavior never applies to
external source adapters.

Dirty-data injection is explicit and testable: duplicate patient IDs, missing
values, invalid ages/dates, discharge-before-admission, inconsistent sex codes,
lab aliases, bilirubin unit variation, negative measurements, diagnosis
inconsistency, and duplicate laboratory rows. The generator returns typed
Pydantic contracts; fields that are intentionally dirty are represented in a
way that permits the source data to remain faithfully dirty.

`make pipeline` selects the active source snapshot (or an explicitly supplied
`--snapshot-id`) and creates a named ingestion run. It validates required
source-row identity and source metadata,
then writes raw-zone envelopes in one transaction per source entity. Re-running
the pipeline for an already completed snapshot returns the existing run summary
unless an explicit new run identifier is requested; this is the idempotency
boundary, not a business patient or lab identifier. An explicit new run is
deliberately allowed and creates a separately auditable raw copy tied to that
run. Duplicate patient and lab business IDs therefore persist as separate
source rows and raw envelopes for later quality detection.

Malformed rows are retained in their source table but are written to
`raw.ingestion_rejection`, not `raw.record`. The run summary, emitted as JSON
to stdout and structured logs, contains `source_rows_seen`, `raw_rows_written`,
`rejected_rows`, and rejection counts by error code for every entity. An
unexpected database error rolls back that entity's raw writes and rejection
writes, marks the run failed, and exits nonzero; valid entities committed before
the failure are not destroyed. Basic validation records defects but never
remediates source data.

## Failure handling and observability

Docker Compose contains a one-shot `migrate` service that runs `alembic upgrade
head`; the API declares it completed successfully as a dependency, so `docker
compose up -d` leaves the database migrated before the API becomes available.
`make migrate` is also provided for local command use. Configuration is
validated at startup. An unavailable database, invalid configuration, or failed
migration exits with a nonzero status. Invalid individual source records are
captured as ingestion rejections, with a reason and run identifier, while valid
records continue. The command reports the defined machine-readable summary. No
patient-identifying data is emitted to normal log messages.

`GET /health` is a readiness check in this milestone: it returns
`{"status":"ok","database":"ok"}` only after a lightweight database query;
otherwise it returns HTTP `503` with `{"status":"unavailable","database":"unavailable"}`.
This makes Compose and API smoke tests deterministic.

## Testing and acceptance evidence

Tests cover deterministic generation, visible duplicate business IDs and other
dirty-data fixtures, source validation/rejection capture, idempotent pipeline
execution, Alembic upgrade, and a FastAPI readiness check. `make test` ensures
the Compose PostgreSQL service is running and uses its dedicated test database;
the ingestion integration test is mandatory and must not be skipped in the
documented workflow. An integration case performs `seed → pipeline → seed`
with a new seed, verifies the original completed raw records remain
inspectable, and verifies that the new snapshot becomes the sole active
snapshot.

The README will document exactly:

```bash
docker compose up -d
make seed
make pipeline
make test
make demo
```

`make demo` will run the migration, seed, and ingestion sequence, then print a
summary. Completion is assessed only against Milestone 1 acceptance criteria.

## Assumptions and deferred work

- Docker and Docker Compose are available locally; documentation provides
  equivalent Python commands.
- Generated direct identifiers exist solely in synthetic source storage and
  are never presented as anonymized data.
- "Raw" means an ingestion envelope plus preserved source payload, not a
  canonical or cleaned representation.
- Canonical tables, rule scoring, OMOP mapping, cohorting, privacy policy,
  full lineage, and dataset product artifacts are deferred to later milestones.
