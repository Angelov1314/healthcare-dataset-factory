# Milestone 3 Review and Field Lineage Design

## Scope

Milestone 3 adds an auditable human review loop for mapping definitions and
field-level lineage for canonical outputs. It builds on the approved mapping
registry and canonicalization runs; it does not introduce cohort building,
OMOP, privacy, or a general-purpose frontend.

The selected approach is a focused mapping-review vertical slice. A reviewer
can inspect a mapping suggestion, approve it, reject it, or propose an edited
replacement. Each decision becomes an immutable audit event, and canonical
field lineage can be traced to the specific source field, mapping definition,
and transform run used.

## Persistence and invariants

Add governance tables:

- `mapping_review`: append-only sequence ID, review ID, mapping-definition ID,
  action (`approved`, `rejected`, `edited`), reviewer, nonblank reason, before
  snapshot/hash, optional after snapshot, exact mapping-set ID/version,
  timestamp, and deterministic sequence ordering.
- `mapping_proposal`: proposal ID, immutable parent definition/review IDs,
  draft mapping fields, confidence, evidence, proposer, and creation timestamp.
- `proposal_resolution`: append-only resolution ID, proposal ID, action
  (`accept_for_next_mapping_set` or `reject`), resolver, reason, sequence, and
  timestamp.
- `mapping_conflict_resolution`: append-only definition-level resolution ID,
  mapping-definition ID, action (`resolve_approve` or `resolve_reject`),
  asserted mapping-admin resolver, reason, sequence, and timestamp.
- `field_lineage`: canonicalization run, source snapshot, canonical record ID,
  canonical entity/field, source system/entity/field, exact source-row ID,
  nullable
  mapping-definition ID/hash, transform version, derivation descriptor, and
  details.

Mapping definitions remain immutable. Approve/reject records a review against
the existing definition. Edit creates a new draft proposal; it never changes an
active mapping definition in place. Promotion of an edited proposal to a new
mapping-set version remains a later release action.

Review events are advisory in this unauthenticated MVP: they do not alter an
active definition or a completed canonicalization run. A mapping is queueable
when it has no advisory decision or has an unresolved proposal. `GET
/review-queue` is a work queue and only returns `pending` and
`needs_resolution` items; `GET /mapping-definitions/{id}/reviews` is the full
history/listing and exposes `advisory_approved` and `advisory_rejected` states.
Queue items are definition/proposal pairs. Independent
approve/reject events from different reviewers set `needs_resolution` and may
not clear it. Only a `mapping_conflict_resolution` event resolves definition
conflict; `proposal_resolution` only resolves its named proposal. In this MVP,
each resolver is a caller-asserted
`mapping_admin` role, not authentication or authorization.
State reduction is deterministic by event sequence: a conflict resolution
governs all advisory events at or before its sequence. A later reviewer event
that conflicts with the resolved action reopens `needs_resolution`; an agreeing
event preserves the resolved advisory state. History always returns ascending
sequence order.

Proposal state is derived from immutable events: creation implies `submitted`;
one `proposal_resolution` event implies `resolved`; a subsequent newly created
proposal with the same parent implies the prior proposal is `superseded`. An
edit creates the immutable submitted proposal tied to parent definition/review
IDs and validates a nonblank source/target/rule/evidence payload. An identical
unresolved proposal is rejected with 409. A resolution event requires nonblank
reason, asserted `mapping_admin`, and an unresolved proposal; a second
resolution returns 409. Rejected resolution removes the proposal from the work
queue but preserves it in history. Creating a new
mapping-set version is deferred. Before snapshots are canonical JSON containing
mapping-definition ID, mapping-set ID/version, source/target/rule/confidence,
evidence, and status; SHA-256 of UTF-8 canonical JSON with sorted keys is stored
alongside the snapshot. The PostgreSQL migration adds `BEFORE UPDATE OR DELETE`
triggers that reject mutations to review, proposal, and resolution event rows;
tests prove direct SQL mutation is rejected. This protects database writes in
the local prototype but not privileged database-superuser access.

## API and behavior

- `GET /review-queue?status=...` lists reviewable mappings with source/target,
  confidence, evidence, and latest review state.
- `POST /mapping-definitions/{id}/reviews` accepts action, reviewer, and reason;
  edit additionally accepts a replacement source/target/rule/evidence payload.
- `GET /mapping-definitions/{id}/reviews` returns append-only audit history.
- `POST /mapping-definitions/{id}/conflict-resolutions` accepts
  `resolve_approve`/`resolve_reject`, asserted `mapping_admin`, and nonblank
  reason; it returns 404 for an unknown definition, 409 without a current
  conflict, and 422 for invalid role, action, or reason.
- `GET /mapping-proposals/{id}` returns the proposal and its resolution history;
  `POST /mapping-proposals/{id}/resolutions` accepts the dedicated resolution
  action, asserted `mapping_admin` role, reviewer, and reason.
- `GET /lineage/canonicalization-runs/{id}/fields` filters by canonical entity
  and returns the source-to-canonical field path.

Invalid identifiers and unknown run IDs return 404; a duplicate identical review
action by the same reviewer returns 409. Invalid action, blank reason for
reject/edit, malformed edit payload, or invalid filters return 422. Lists use
`limit` (1–100), opaque cursor pagination, and ascending sequence ordering.
Reviewer identity is a required explicit request field; the system does not
infer or authenticate it. API contracts use Pydantic models.

## Lineage generation

Canonicalization writes one lineage row for every canonical record field it
resolves through the registry. Derived/defaulted fields write a `transform_only`
derivation descriptor with nullable mapping definition. Source values are never
copied into lineage details. Every row names mapping-set version, definition
hash where applicable, source snapshot, and transform version, so an inspector
can answer: which source row/field became this output field, under which mapping,
in which run? `GET /lineage/canonicalization-runs/{id}/fields` supports
canonical entity, canonical record ID, canonical field, and source-row ID
filters.

## Tests and acceptance

PostgreSQL tests cover queue/needs-resolution state, approve/reject/edit audit
immutability, duplicate-action conflict, reviewer-required validation, proposal
state transitions, rejected update/delete attempts, stable sequence ordering,
resolution role/reason/state/idempotency failures, definition-conflict clearing,
cursor-stable queue results, and record-level lineage retrieval for patient sex/date and normalized
measurement fields. Existing pipeline tests must still pass. The README
documents curl examples and clearly labels the review queue as mapping-only and
unauthenticated attribution for this milestone.
