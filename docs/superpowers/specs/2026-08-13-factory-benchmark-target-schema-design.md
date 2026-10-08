# Factory Benchmark Target Schema Design

## Purpose

Add an isolated `factory-benchmark@1.0.0` target-schema registry so the
synthetic CSV bundle can evaluate import mapping against its full Factory
Canonical Model. The existing `liver-core` target registry and synthetic
execution path remain unchanged.

## Source of truth and anti-leakage boundary

`Healthcare_Dataset_Factory_Synthetic_Test_Data_v1_csv_bundle/Gold_Field_Mapping.csv`
is authoritative only for the set of canonical targets in this benchmark
registry. The implementation may extract and normalize its unique non-empty,
non-`UNMAPPED` target values at development time, then store the registry in
source code. It must not read or persist source-sheet/source-field to target
pairs, expected methods, expected decisions, difficulty labels, or notes in
the retrieval service. Gold source-to-target pairs are used only by the offline
benchmark evaluator.

The registry version and an ordered registry fingerprint are recorded in each
retrieval candidate and benchmark result. Registry changes require a new
version.

## Registry and domain contracts

The registry contains 116 unique canonical targets from the bundle. Gold has
118 mapped source-field pairs; two pairs share targets. The registry is represented as
four fields:

`target_entity`, `target_field`, `domain`, and a hand-authored neutral target
description derived only from the canonical target name. No source aliases are
included in descriptions. The artifact is a source-controlled ordered JSON
array, serialized as UTF-8 JSON with sorted object keys and NFC-normalized
strings. Its SHA-256 is the registry fingerprint. A new target or description
requires a new registry version; an existing version/fingerprint pair is
immutable.

Supported domains are:

- `patient`
- `encounter`
- `condition`
- `measurement`
- `drug_exposure`
- `procedure`
- `provenance`

Domain selection is a deterministic field-name/type/unit classifier. Its
canonical vocabulary is exactly the seven domains above; legacy `visit` maps to
`encounter`, and legacy `drug` maps to `drug_exposure`. If it has no confident
domain it searches the full selected registry rather than silently dropping
candidates. The current `liver-core@1.0.0` remains the default for the normal
product flow. The benchmark request explicitly selects
`factory-benchmark@1.0.0`.

Benchmark persistence is isolated from ordinary import suggestions and
`mapping_candidate`: it has an immutable `BenchmarkRun`,
`BenchmarkProfileSnapshot`, and `BenchmarkCandidateSnapshot` keyed by run,
profile hash, registry version/fingerprint, and retrieval version. Normal
`ImportJob` manifests and current mapping candidates are never changed by a
benchmark. Each snapshot records `(registry_version, registry_fingerprint,
retrieval_version, benchmark_mode=true)`. A rerun creates a distinct immutable
benchmark run but uses exactly the same candidate ranking whenever those
versions and profile hashes are equal.

## Retrieval and benchmark flow

For each imported safe field profile, `BENCHMARK_RETRIEVAL_ONLY` uses the
selected target registry to run local BM25 and deterministic hashed-vector
retrieval, domain filter, fusion, deduplication, and top-five selection. It
does not consult historical mappings, exact/alias/vocabulary rules, prior
reviews, mapping definitions, or LLM reranking. The requested baseline is
always `BENCHMARK_RETRIEVAL_ONLY`; any later HYBRID report is a separately
versioned run and labels its optional rerank outcomes separately.

reports:
An offline benchmark evaluator reads Gold Mapping only after retrieval. It
first validates the bundle identity by comparing every import job's immutable
artifact hash, display name, ordered source-header/profile fingerprint, and the
bundle manifest's expected sheet/row-count contract. The bundle manifest itself
is hashed and stored with the run. The evaluator also stores an NFC-normalized,
canonical-CSV SHA-256 fingerprint of the complete Gold Mapping fixture and its
own metric-policy version `factory-benchmark-evaluator@1.0.0`; Gold content is
not returned. Missing, duplicate, substituted, or
out-of-contract sheets reject the run.

Top-1 and Top-5 evaluate the raw local retrieval ranking only. A field has one
Gold target or `UNMAPPED`; any other Gold shape rejects the fixture. Coverage is
the fraction of Gold-mapped fields with at least one candidate. The decision
threshold is versioned as `factory-benchmark-decision@1.0.0`: a field is
`review_required` only when its best fusion score is at least 0.10, otherwise
it is `unmapped`. Abstention accuracy is the fraction of Gold `UNMAPPED` fields
below that threshold. Review-required and unmapped rates use all 123 fields as
their denominator. It reports:
reports:

- total fields and gold-mapped fields;
- Top-1 and Top-5 target accuracy for mapped fields;
- abstention accuracy for `UNMAPPED` targets;
- coverage, review-required rate, and unmapped rate;
- metrics grouped by source sheet and difficulty;
- registry version/fingerprint, retrieval version, and import job IDs.

It stores only aggregate results and hashes/versions; no source cell values,
direct identifiers, credentials, or Gold source-to-target pairs are exposed by
the API or UI.

## API and UI

`POST /benchmarks/factory` accepts the six named import-job IDs corresponding
to the source sheets and runs local retrieval + offline aggregate evaluation.
It returns a new immutable benchmark run ID. It rejects missing, duplicate, or
non-bundle source sheets and returns safe counts and metric groups only.

`GET /benchmarks/factory/{run_id}` returns that immutable aggregate report.
The feature is explicitly restricted to the bundled synthetic fixture in this
unauthenticated prototype; it must not select a global “latest” report. The
Import & Map page displays the selected registry version and links only to a
run ID returned in the current browser session. The Mapping Workbench continues
to show candidates from the registry selected for the corresponding import job.
It does not display Gold answers.

## Testing and acceptance

Tests must verify that:

1. the factory registry contains the expected 116 unique targets and its
   fingerprint is stable;
2. liver-core retrieval remains unchanged;
3. factory retrieval returns only factory registry targets and preserves local,
   deterministic behavior;
4. the benchmark evaluator never passes Gold source-target pairs to retrieval,
   rules/history/review/LLM layers, or persisted candidate/suggestion/audit
   records, using a canary Gold fixture to prove the boundary;
5. bundle identity validation rejects substituted, duplicate, reordered, and
   out-of-contract sheet inputs, while a repeated valid run produces stable
   aggregate metrics;
6. benchmark API/UI responses and error payloads contain no raw source values,
   credentials, or per-field Gold answers, and no benchmark endpoint exposes a
   cross-run global report;
7. a fresh test database can migrate all new structures and the full suite
   passes.

The first acceptable run is a truthful baseline: it may have low accuracy. The
purpose is to make the target-schema mismatch measurable before improving
rules, retrieval, or optional LLM reranking.
