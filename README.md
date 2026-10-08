# Healthcare Dataset Factory

This local, synthetic-data prototype demonstrates a small Healthcare High-quality
Dataset Factory: source ingestion, governed canonical data, quality checks,
deterministic OMOP-lite mapping, a versioned liver cohort, and an opt-in
pseudonymized dataset export. It is an engineering MVP for reproducible demos,
not a production clinical data platform or a guarantee of anonymization.

The repository contains source code, migrations, tests, and design documentation
only. It does not include patient data, generated exports, database volumes, or
provider credentials. All generated records are synthetic; raw fixtures may
intentionally contain identifier-like fields to exercise governance checks.

## Publication validation (2026-10-08)

The public source snapshot passed Python syntax checks for 53 files and a
basic smoke check. Pytest collected 24 tests, but all stopped during database
fixture setup because the publication host had no running PostgreSQL service
or Docker Compose. This is not a passing integration-test result. Run the
Compose setup and `make test` below before relying on the full pipeline.

## Prerequisites

- Docker Desktop with Docker Compose v2
- GNU Make (or run the equivalent commands below)

Copy the supplied environment template only if you need to change defaults:

```bash
cp .env.example .env
```

## Run the prototype

```bash
docker compose up -d
make seed
make pipeline
make canonicalize
make quality
make semantics
make product
make pipeline-all
make demo
make test
```

`docker compose up -d` starts PostgreSQL, runs Alembic migrations through the
one-shot `migrate` service, and then starts the API. Verify readiness at
<http://localhost:8000/health>. PostgreSQL is exposed on host port 5433 by
default to avoid clashing with an existing local PostgreSQL server; set
`POSTGRES_PORT` in `.env` to choose another host port.

## Import and mapping suggestions

Open <http://localhost:8000/imports/console> to upload a CSV or Excel file.
The Stage 1 import flow only profiles headers, inferred types, units, and
aggregate safe summaries; it does not retain example cells or directly execute
any mapping. Suggestions follow a deterministic order: approved mapping history,
exact canonical field name, local vocabulary aliases, generic aliases, then
abstention. Every positive suggestion remains `review_required`.

The PostgreSQL API accepts a selected schema and table only—not arbitrary SQL.
It enforces the configured `IMPORT_ALLOWED_POSTGRES_HOSTS`,
`IMPORT_ALLOWED_POSTGRES_PORTS`, row cap, and short read-only timeout. Database
credentials are request-only in this stage and are not stored.

For every profiled field, the local retrieval service also stores up to five
candidate targets. It combines a BM25 lexical score with a deterministic
hashed-vector similarity score, filters to a selected clinical domain when
possible, and keeps the score evidence in PostgreSQL. This stage has no network
dependency and does not call an LLM. The safe candidate projection is available
at `GET /imports/{import_job_id}/candidates`.

Optional AI reranking is disabled until `DEEPSEEK_API_KEY` is configured in the
runtime environment. The provider receives only the safe profile metadata and
the existing target candidates; it can choose one of those candidates or
abstain. A missing key, timeout, malformed response, or invalid target preserves
the local candidates and records a safe fallback audit event. Neither prompts,
raw provider responses, nor secrets are persisted.

Use the Mapping Workbench at <http://localhost:8000/mapping/workbench> after an
import. Select a retrieved target candidate, then approve it; alternatively
edit to another registered target, reject it, or mark it unmapped. Decisions are
append-only. “Publish approved version” creates a deterministic draft mapping
registry version from only approved/edited decisions. It does not yet execute
an external source dataset; this keeps mapping governance separate from any
future execution and quality gate.

## Factory synthetic benchmark

The optional factory benchmark evaluator can score a compatible synthetic CSV
bundle against the isolated `factory-benchmark@1.0.0` target registry. The
bundle is intentionally not included in this public source snapshot: it
contains benchmark source rows and Gold mappings that are not needed to run the
core pipeline. If you have an approved synthetic bundle, it should contain 116
unique canonical targets and all 123 source fields (118 mapped Gold pairs and 5
`UNMAPPED` pairs) in `BENCHMARK_RETRIEVAL_ONLY` mode. This mode never uses
historical mappings, aliases, human reviews, LLM reranking, or Gold answers to
produce candidates.

Mount the bundle into the runtime and set `FACTORY_BENCHMARK_BUNDLE_PATH` to
its in-container path. Then use <http://localhost:8000/benchmarks/console>,
paste the six import-job IDs, and run the benchmark. The console reports only
aggregate metrics and an immutable run ID; Gold answers and source cell values
remain unavailable through the API.

`make seed` writes a deterministic synthetic source snapshot (2,000 patients by
default). The generator deliberately includes duplicates, missing identifiers,
mixed date formats, sex-code variation, lab aliases, bilirubin unit variation,
negative measurements, inconsistent diagnoses, and duplicate lab rows.

`make pipeline` validates source-row identity and loads valid source rows into
`raw.record`. Invalid rows are retained in the source schema and recorded in
`raw.ingestion_rejection`. It prints one JSON run summary. Re-running it returns
the completed run summary; use an explicit `--new-run` for a separate audited
run.

`make canonicalize` seeds the approved `liver-core@1.0.0` mapping set when
needed, then produces canonical patient, visit, condition, and measurement
records from the completed raw ingestion run. `make quality` persists 22
versioned, transparent quality-rule results with before/after population counts,
six dimension scores, and job-level lineage. `make pipeline-all` runs the full
Milestone 2 synthetic path in sequence. `make semantics` maps the completed
canonical run into the local `HDF_LOCAL@1.0.0` OMOP-lite vocabulary and runs
the append-only `liver-cohort@1.0.0` definition. Its output intentionally
contains only a cohort member count, not source or patient identifiers.

`make product` creates a pseudonymized, synthetic CSV and JSON Dataset Card in
`exports/`. The default policy retains exact dates and province, while removing
source IDs, DOB, city, names, phone numbers, and raw payloads. Set a non-empty
local secret before running it; the secret is never written to the database or
exported artifact:

```bash
export PSEUDONYMIZATION_SECRET='a-local-development-secret'
make product
```

For a fresh end-to-end demo after changing canonical schemas, seed a new
snapshot before running the pipeline:

```bash
docker compose exec -T api python -m app.cli seed --seed 20260811 --patients 2000
make pipeline
make canonicalize
make semantics
```

`make demo` repeats the seed and pipeline commands. `make test` runs pytest
against the Docker-provisioned `healthcare_factory_test` PostgreSQL database.

The current test suite is integration-oriented and expects the Compose database
to be available. The optional AI reranking path is disabled unless a runtime
`DEEPSEEK_API_KEY` is supplied; the deterministic local mapping path works
without network access.

## Equivalent commands without Make

```bash
docker compose up -d
docker compose exec -T api python -m app.cli seed
docker compose exec -T api python -m app.cli pipeline
docker compose exec -T api python -m app.cli canonicalize
docker compose exec -T api python -m app.cli semantics
docker compose run --rm -e DATABASE_URL=postgresql+psycopg://healthcare:change_me@db:5432/healthcare_factory_test api pytest
```

## Developer commands

```bash
make migrate
make down
```

The command-line seed can be configured without editing code:

```bash
docker compose exec -T api python -m app.cli seed --seed 20260811 --patients 1000
```

All generated data is synthetic. Source tables may contain direct-identifier-like
synthetic fields strictly to model raw HIS input; this does not constitute
anonymized or de-identified data.
