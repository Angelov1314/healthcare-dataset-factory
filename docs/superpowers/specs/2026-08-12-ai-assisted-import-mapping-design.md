# AI-Assisted Import and Mapping v1 Design

## Authority and scope

`CODEX_MAPPING_HANDOFF_SINGLE_FILE.md` is authoritative for the mapping/import
subsystem and supersedes older documents where they conflict. This feature is a
separate five-stage program. Each stage is independently tested and reviewed;
later stages cannot weaken the deterministic safety guarantees of earlier ones.

Supported first-release inputs are CSV, Excel, and PostgreSQL. A source can use
a session-only connection or a saved connection. All data remains synthetic in
this prototype. No LLM output is allowed to mutate raw or canonical data.

PostgreSQL import is schema/table selection only—never arbitrary SQL—and uses a
least-privilege read-only source role. It rejects hosts/ports outside configured
allowlists, sets connection/query timeouts and row/byte limits, and never writes
to the source database. The UI states this before a connection is tested.

## Credential safety

Session credentials are held only in memory and discarded after the import job.
Reusable credentials use a `CredentialStore` interface: macOS tries Keychain
first; if unavailable, the application encrypts an envelope using
`CREDENTIAL_ENCRYPTION_KEY`; if neither is usable, saving is rejected while
session-only import remains available. Stored metadata includes an opaque ID,
provider/type, display name, and timestamps—not plaintext credentials. Secrets
never appear in APIs, logs, errors, Dataset Cards, or Git.

The DeepSeek provider reads `DEEPSEEK_API_KEY` from environment or a credential
handle. It uses the official OpenAI-compatible API at
`https://api.deepseek.com`, JSON-object mode, and configurable model default
`deepseek-v4-flash`. The provider interface is swappable. No API key is
embedded in fixtures or documentation; any previously exposed key must be
revoked and replaced by the user.

## Mapping pipeline

The default `HYBRID` mode follows exactly:

`profile → history/exact/alias/vocabulary → domain selection → BM25 + local dense retrieval → bounded context → optional LLM rerank → abstention → human review → versioned mapping → deterministic execution`.

`RULE_ONLY` skips LLM calls. `AI_ASSISTED` may call the provider more often but
has the same review and non-writeback rules. Mapping decisions do not use a
weighted average of rule and LLM scores. Historical/exact/vocabulary matches
may be eligible for policy-configured auto-map; all LLM-involved and conflicting
suggestions require review. Insufficient separation or unsupported targets
abstains to review/unmapped. LLM outage, timeout, or malformed JSON continues
with retrieval plus review; no threshold becomes more permissive.

Before any profile, retrieval, log, UI projection, or DeepSeek egress, a shared
classifier applies an allowlist. It permits schema metadata (source table/field,
type, unit, sibling names, structural hints) and synthetic/redacted summaries
only. It rejects source record IDs, raw values, patient/direct identifiers,
credentials, and unclassified text rather than attempting best-effort masking.
LLM context is bounded to those permitted fields, selected domain/table, top
5–10 candidates, and confusable candidates; it never includes the full target
schema. Output is strict JSON with candidate target, transform proposal,
confidence, evidence, abstention flag, provider/model/version, and validation
status.

## Stage 1 — import foundation

Implement import jobs, file uploads for CSV/Excel, PostgreSQL schema/table
selection, raw landing metadata, schema profiling, field profiles, target-schema
registry, historical mapping lookup, exact/alias/medical-vocabulary rules,
mapping suggestions, and audit events. Profiles include only metadata and safe
sample summaries. The mapping UI has an Import wizard and an initial suggestion
list with source name/type/unit, target, confidence, evidence, route, and
status. No LLM/retrieval implementation occurs in this stage.

## Stage 2 — hybrid retrieval

Implement table/domain selection, BM25 top-30, local dense top-30 behind a
provider interface, fusion/deduplication, target-domain filtering, final top-k,
and benchmark instrumentation. All retrieval works with no network or LLM.

## Stage 3 — DeepSeek rerank and fallback

Implement provider-neutral `LLMMappingProvider`, DeepSeek JSON-mode adapter,
bounded context packing, response validation, timeout/retry, auditable model
metadata, and automatic fallback. Invalid or unavailable provider responses
must yield retrieval candidates plus a review-required status.

## Stage 4 — human review and deterministic execution

Add a mapping workbench with Approve, Edit target, Edit transform, Reject, Mark
unmapped, and policy-limited Override. Reviews persist the profile/candidate
snapshot, rules/vocabulary/provider/model versions, reviewer/comment, final
transform and mapping version/supersession relation. Only approved registry
versions feed a deterministic executor; repeat execution of equal source and
mapping version must match, without an LLM call. The executor runs the existing
quality gate, writes canonical/specialty outputs only on policy-acceptable
quality status, and persists field/job lineage. Quality failure produces an
audited failed execution without publishing downstream dataset-product metadata.

## Stage 5 — benchmark and console completion

Create a 100-field synthetic clinical benchmark (including aliases, Chinese and
English forms, units, ambiguity, and confounders), compare rule/retrieval/LLM
modes, and persist hit rates, abstention accuracy, review rate, acceptance/edit
rate, time per 100 fields, and provider calls/cost when available. The existing
console gains import and mapping-review views wired to the real APIs, with no
source values, credentials, raw IDs, member IDs, or filesystem paths sent to
the browser.

## Acceptance and tests

Tests cover CSV/Excel/PostgreSQL session import, safe saved credential fallback,
profile redaction, historical/exact/alias/vocabulary routing, audit manifests,
LLM-disabled operation, malformed/timeout DeepSeek fallback, strict JSON
validation, review versioning, deterministic replay, and benchmark metrics.
Browser tests cover the import wizard and review decisions using only safe
metadata. Every import/run manifest immutably records hashes/versions for the
source artifact and profile, target-schema registry, mapping policy, retrieval
index/embedding model, bounded prompt/context, candidate set, provider response,
executor, and quality rules, plus output manifest/lineage. All API, prompt, and
log payloads are scanned recursively for credentials, source record IDs, raw
values, and patient/direct identifiers; safe schema metadata is explicitly
allowed.
