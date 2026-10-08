# Mapping Accuracy Foundation Design

## Authority and scope

This design implements the user's approved operating policy: **automatically
publish only high-confidence mappings; create review tasks for all other
plausible mappings; abstain from fields that have no supported target**.

It is an accuracy and policy layer for the existing import-mapping subsystem.
It does not execute source-to-canonical transformations, change raw or
canonical data, add a new UI surface, or turn the optional DeepSeek provider
into an autonomous mapper.  The existing import console and Mapping Workbench
remain the user interface for suggestions and review.

The current `factory-benchmark@1.0.0` remains a frozen synthetic evaluation
fixture.  Its Gold mapping is read only by the evaluator after candidates and
decisions have been generated.  No Gold source-field/target pair, answer, or
test-specific exception may enter registry metadata, rules, prompts, or the
auto-publish policy.

## Goals

1. Improve local candidate recall by taking source-table entity, field type,
   unit, and target metadata into account.
2. Make an explicit, reproducible decision for every field:
   `auto_published`, `review_required`, or `unmapped`.
3. Make automatic publication safe, idempotent, versioned, and auditable.
4. Retain a network-independent baseline; DeepSeek remains an optional,
   candidate-bounded reranker and never creates new targets.
5. Report accuracy and decision metrics without persisting Gold answers or
   source values in benchmark artifacts.

## Non-goals

- Training on, copying from, or hand-tuning against the supplied Gold Mapping.
- Free-form LLM mapping, automatic data execution, or automatic deletion.
- Persisting source cells, patient identifiers, credentials, prompts, or model
  responses.
- Guaranteeing semantic correctness for unsupported source systems; uncertain
  mappings must be reviewable.

## Chosen approach

Three alternatives were considered:

1. **LLM-first mapping.** It can explain choices but cannot recover a correct
   target absent from the candidate list and would increase data-egress risk.
2. **More aliases only.** It improves some abbreviations but cannot distinguish
   `condition.patient_id` from `encounter.patient_id` when the source field is
   the same.
3. **Context-aware local retrieval, policy decision, then optional LLM
   reranking.** This is the chosen approach. It first improves recall with
   source structure and target facets, then uses calibrated policy to decide
   publication, review, or abstention. An LLM may only reorder the local list.

## Data contracts

### Source context

Each `SourceFieldProfile` supplies only its existing metadata-safe fields:
`table_name`, `field_name`, ordinal, inferred type, detected unit, and safe
summary.  A new pure resolver derives a `source_entity` from a normalized table
name. The initial supported table/entity mappings are:

| Source table family | Source entity |
| --- | --- |
| patient, demographic | patient |
| visit, encounter, admission | encounter |
| diagnosis, condition | condition |
| lab, result, measurement, lis | measurement |
| medication, drug, prescription | drug_exposure |
| procedure, operation | procedure |

If no family is recognized, the context is `unknown`; this cannot satisfy the
automatic-publication entity condition.

The resolver may use generic target-side clinical vocabulary and common
abbreviation normalization, but may not contain fixture-specific source/G​old
pairs. `patient_id`, `visit_id`, and equivalent relationship names are
interpreted relative to the source entity: for example, in a diagnosis row a
patient relationship is a `condition.patient_id`, not `patient.patient_id`.

### Target registry facets

The factory registry remains a **frozen benchmark-only** target artifact. It is
not an executable production mapping registry and it may contain targets that
are intentionally unavailable to product mapping (including direct-identifier
targets). Benchmark candidates are never auto-published.

Production imports use a separate `production-canonical@<version>` registry.
Its targets are generated from, and validated against, the executable canonical
and specialty model. The registry explicitly allowlists targets eligible for
mapping; direct identifiers, raw-source fields, deprecated targets, and any
benchmark-only target are absent. A target must be both in this registry and
declared executable by the canonical model before candidate scoring and again
immediately before publication. Failure at either point produces `unmapped`
with `unsupported_target` and cannot be overridden automatically.

Each target-only production entry has, in addition to `target`, `domain`, and
description:

- `entity` and `field`;
- `semantic_kind`: `identifier`, `relationship_identifier`, `code`, `text`,
  `datetime`, `numeric`, `unit`, `flag`, `provenance`, or `unknown`;
- `value_type`: `string`, `integer`, `decimal`, `boolean`, `date`,
  `datetime`, or `unknown`;
- optional `unit_family` (for example liver enzyme, bilirubin, mass, length);
- target-side clinical description and general synonym tokens.

Descriptions are canonical-target metadata, not source examples. The registry
fingerprint covers every facet plus the executable-model compatibility manifest.
Changing it creates a new registry version.

### Candidate contract

`production_candidates` is the only candidate-generation entry point eligible
for import decisions or publication. It accepts `table_name`, `field_name`,
inferred type, unit, a production-registry compatibility manifest, and the
production registry fingerprint; it returns up to 20 deterministic local
candidates. `factory_candidates` remains benchmark-only and has no call path to
production import, decision, review, or publication code. Every production
candidate
contains the existing scores plus:

- `entity_match` (`exact`, `relationship`, `cross_entity`, `unknown`);
- `type_compatible` (boolean);
- `unit_compatible` (`true`, `false`, `not_applicable`);
- `semantic_kind` and `target_metadata_version`.

Candidates with an incompatible declared type or unit are excluded unless that
would leave no candidate. Unknown types remain eligible but cannot receive an
automatic-publication decision. Every candidate, decision, and publication
evidence record carries the production registry version/fingerprint and
compatibility-manifest fingerprint. Sorting uses an explicit deterministic
tuple: context compatibility, hybrid score, lexical score, target string.

Initial retrieval is deterministic local hybrid retrieval: normalized token and
character n-gram lexical scores plus the existing local hashed semantic score.
It takes the union of lexical and semantic candidate pools, deduplicates by
target, applies compatibility filtering, and returns the first 20. There is no
network call. The UI and current candidate persistence may show the first 10;
the benchmark evaluates Top-1, Top-5, and candidate recall at 20.

### Decision contract

A pure `decide_mapping` function receives source context and ordered
candidates. It returns exactly one result:

| Status | Meaning |
| --- | --- |
| `auto_published` | A high-confidence, deterministic mapping was versioned automatically. |
| `review_required` | A plausible mapping exists, but it is not safe to publish automatically. |
| `unmapped` | No supported target is asserted. |

The initial policy version is `mapping-auto-policy@1.0.0`. A mapping is
eligible for `auto_published` only when all conditions hold:

1. the source entity is known and matches the target entity, or is a known
   relationship field for that entity;
2. source and target types are compatible, and any known unit is compatible;
3. no risk classifier marks the field as free text, a local/legacy technical
   key, batch identifier, or unsupported sensitive identifier;
4. candidate score is at or above the policy's fixed high-confidence threshold;
5. the Top-1 / Top-2 score margin is at or above the fixed ambiguity threshold;
6. the choice comes from a deterministic local rule or local retrieval, not an
   LLM result alone.

The exact thresholds are immutable named constants in the policy and included
in a policy fingerprint. They must be calibrated only against a separate,
versioned synthetic validation fixture or approved historical mappings—not the
frozen Gold benchmark. Until validation data exists, the policy starts in
**conservative mode**: only exact canonical and vocabulary mappings that meet
conditions 1–3 may auto-publish. All other candidates require review.

Risk classification is a deny-by-default policy for unsupported free text and
technical identifiers. It is never a claim that a field is anonymous, and it
does not discard data; it only decides mapping status. `unmapped` results must
include a bounded, safe reason code such as `unsupported_free_text`,
`technical_identifier`, `unknown_source_entity`, `low_confidence`, or
`ambiguous_candidates`.

## Lifecycle and audit

Import jobs are immutable after profiling. For each profile, the system stores
the candidate snapshot and policy decision evidence. `auto_published` creates
one `MappingSuggestion` with an append-only system review (`reviewer=system`)
and a corresponding `MappingDefinition` in an immutable mapping set. The
definition has status `approved`, a policy-derived version/scope, and evidence
that includes profile hash, target registry version/fingerprint, retrieval
implementation/index version and fingerprint, policy version/fingerprint,
decision inputs, selected candidate rank, and a no-raw-data evidence hash.

Creation is transactionally idempotent using `(import_job_id,
source_field_profile_id, production_registry_fingerprint,
retrieval_implementation_fingerprint, retrieval_index_fingerprint,
policy_fingerprint)` as the logical identity, enforced by a transactional
uniqueness constraint on the automatic-decision record. A repeated identical
request returns the existing automatic definition/review without adding a
second one. A changed profile, production registry, retrieval implementation or
index, or policy produces a new immutable mapping set version rather than
altering an old mapping.

The existing one-final-review-per-suggestion rule remains true. A human cannot
append a second review to an automatically reviewed suggestion. Instead, the
Review Queue creates one linked successor suggestion with
`supersedes_mapping_suggestion_id` pointing to the automatic suggestion and a
unique `(supersedes_mapping_suggestion_id, correction_policy_fingerprint)` key.
The successor carries a fresh candidate snapshot and permits exactly one human
review. Publishing the correction creates a successor mapping-set version with
explicit `supersedes_mapping_definition_id` evidence. The original automatic
review, definition, and audit record remain immutable.

`review_required` suggestions are persisted exactly as today, with candidate
and policy evidence. `unmapped` suggestions have no target and are visible in
the workbench with their safe reason. Neither creates an executable mapping.

## Optional DeepSeek behavior

DeepSeek runs only after local candidates and a **provisional** local policy
decision exist. It receives the existing bounded safe context, extended only
with source entity and target facets. Identifier-like and unsafe fields are
rejected before any call. It may select only from the supplied candidates or
abstain. Its result can lower an automatic eligibility result to
`review_required`, but can never raise a local candidate to `auto_published`.

If reranking is enabled for an import, the service first computes and records
the provisional decision, then awaits a completed, unavailable, invalid, or
fallback provider outcome; only then does one transaction persist the final
suggestion plus any system review and automatic definition. Thus an LLM
downgrade never changes an already published immutable decision. If reranking
is disabled, rejected by the safety classifier, unavailable, invalid, or times
out, the final decision equals the local provisional decision and the bounded
outcome status is included in evidence. Provider outage, invalid JSON, or
timeout never makes the local policy more permissive.

## Benchmark and acceptance

The factory benchmark snapshots candidates before reading Gold and persists
only source-safe profile hashes, candidate ranking metadata, registry and
policy fingerprints, and aggregate metrics. It calls the benchmark-only
retrieval/policy evaluator in **dry-run mode**: no system review, mapping
definition, executable mapping set, or successor relation is created. Its
“automatic publication” metrics mean only that a simulated decision would meet
the production policy conditions. It adds:

- candidate recall@20 for mapped fields;
- Top-1 and Top-5 accuracy for mapped fields;
- correct abstention rate for Gold `UNMAPPED` fields;
- automatic-publication count, precision, and coverage;
- review-required count and rate;
- decision counts by source sheet and difficulty.

No release gate is based on a hard-coded score target. It must demonstrate a
strict improvement over the baseline's 52.5% Top-1, 74.6% Top-5, and 0%
correct abstention on the same fixture, while preserving deterministic output.
Any metric regression blocks automatic-policy expansion; it does not make the
policy more permissive.

Required tests include:

1. deterministic candidates and candidate ordering for the same profile;
2. source-table-relative relationship mappings for patient and encounter IDs;
3. compatibility rejection for mismatched types and units;
4. source-target registry has no Gold source aliases or raw examples;
5. each status transition and its exact safe reason;
6. `factory_candidates` cannot be called by production imports, and production
   candidates carry production registry/compatibility fingerprints;
7. an LLM result cannot cause automatic publication, and final publication is
   committed only after a configured rerank outcome is known;
8. production registry rejects benchmark-only, prohibited, and non-executable
   targets before decision and publication;
9. idempotent automatic mapping-set creation includes registry/retrieval/policy
   fingerprints, and correction uses one linked successor suggestion rather
   than a second review;
10. benchmark dry-run cannot create executable mapping records, and recursive
   checks that API/audit/prompt projections omit raw values,
   credentials, direct identifiers, and Gold answers;
11. full benchmark determinism and aggregate-only result persistence.

## UI and documentation

The existing import console displays `Auto-published`, `Review required`, or
`Unmapped`, plus a safe reason and confidence. The Mapping Workbench can filter
to human review items, show source entity/type/unit and candidate compatibility,
and distinguish an automatic system decision from a human decision. It never
shows source values, credentials, raw record IDs, or Gold benchmark labels.

README documentation adds an Accuracy Foundation section describing the three
decision outcomes, automatic-publication limits, how to inspect an automatic
mapping set, how to correct it through review, and how to run the synthetic
benchmark.
