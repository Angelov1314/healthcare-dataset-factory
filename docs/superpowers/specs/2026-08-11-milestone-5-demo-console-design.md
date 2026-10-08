# Milestone 5 Demo Console Design

## Goal

Add a no-build-step, FastAPI-served HTML console that demonstrates the complete
synthetic-data story: Sources → Mapping → Quality → Review → Cohort → Dataset
Product. It is a real operator console, not a static mockup: actions call
existing APIs and refresh public, count-only summaries.

## UI and interactions

`GET /` serves a lightweight responsive HTML/CSS/JavaScript document with six
navigation views. The Pipeline home view shows source count, raw record count,
mapped fields, quality score, pending review count, cohort member count, and
dataset-product status. It has actions to refresh, run quality, run cohort,
and generate a product pack. Actions must disable while in flight, display a
success/error status, then re-fetch summaries.

Each module view uses existing public endpoints: Mapping shows registry
definitions, Quality shows score/dimensions, Review shows the queue, Cohort
shows count-only preview/run result, and Dataset Product shows count/Card.
The client never receives or renders source patient IDs, source-row IDs,
member IDs, raw payloads, names, phone numbers, or identity numbers.

## API consolidation and safety

`GET /dashboard` returns only `{sources, raw_records, mapped_fields,
quality_score, review_pending, cohort_members, product:{status, patient_count}}`.
No UUID, lineage hash, path, policy metadata, exception text, or source/member
identifier is permitted. The server recursively validates response keys and
serialized values against the forbidden identifier list before emitting JSON.

The console uses dashboard-safe projections only: `/dashboard`,
`/dashboard/mapping` → `{mapped_fields, active_version}`, `/dashboard/quality`
→ `{overall_score, dimensions}`, `/dashboard/review` → `{pending_count}`,
`/dashboard/cohort` → `{status, member_count}`, and `/dashboard/product` →
`{status, patient_count, record_count, version}`. These exact allowlists are
the only module data contracts. It never fetches raw, lineage, or existing
ID-bearing endpoints.

`POST /dashboard/actions/quality` selects the newest completed canonical run
for the current active snapshot; `/cohort` selects the newest completed OMOP
run for that canonical run and the seeded definition; `/product` selects the
newest completed cohort and quality run matching that same canonical run.
Newest means `created_at` descending, then UUID descending; completed downstream
runs are reused by the service rather than recomputed. Successful action replies
contain only `{status, quality_score? , member_count?, patient_count?}`.
Product generation requires a non-empty secret and never returns a filesystem
path. No browser endpoint exposes CSV contents in this milestone.

All action errors use `{code, message}` from a fixed public set:
`empty_system`/`dependency_missing` → 404, `job_in_progress`/`job_failed` →
409, `privacy_not_configured` → 422, and `action_failed` → 422. They never
relay raw exceptions, configuration, paths, or input identifiers. The response
guard reuses M4's forbidden terms (`name`, `id_number`, `phone`,
`source_patient_id`, `source_visit_id`, `source_row_id`, `date_of_birth`,
`city`, `payload`), lowercases recursive JSON keys and serialized values, and
rejects any substring match before response emission.

## Validation

Tests verify the console HTML has no server-side data interpolation; recursively
check dashboard, action success, and action error keys/values for forbidden
identifiers; assert deterministic selection with multiple runs and idempotent
repeat clicks; and cover empty/missing/started/failed/secret-missing states.
Browser verification checks all six views plus a successful update and a
disabled-action/error-banner state followed by refresh.
