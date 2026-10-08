# Milestone 4 Privacy and Dataset Product Design

## Scope and fixed choices

This milestone turns a completed liver cohort into a reproducible, synthetic
dataset product. Product rows retain exact clinical dates and province only;
city is removed. The export format is one CSV data file plus a JSON Dataset
Card. This is pseudonymization and field minimization, not a claim of full
anonymity or clinical safety.

No real patient data, clinical decision logic, UI redesign, Parquet export,
external storage, or access-control system is included.

## Privacy policy and product schema

Add a `product` schema with append-only `privacy_policy`, `dataset_product`,
and `export_attempt` records. A policy contains an explicit, versioned field
contract: `date_mode` (`exact` or `per_patient_shift`), `age_mode` (`exact` or
`bands_10y`), and `geography_mode` (`province_only` or `remove`). The seeded
`liver-product-policy@1.0.0` uses the user-selected defaults `exact`, `exact`,
and `province_only`; alternate modes are configurable policy data and tested.
Its field rules:

- remove `name`, `id_number`, `phone`, `source_patient_id`, source row IDs,
  source visit IDs, and city;
- replace the canonical patient ID with a deterministic HMAC-SHA256
  pseudonymous ID using `PSEUDONYMIZATION_SECRET` from environment settings;
- retain only allowlisted output columns: `pseudonymous_patient_id`, `age`,
  `province` (unless removed), `first_visit_date`, `last_visit_date`,
  `liver_condition_codes`, `alt_max`, `ast_max`, and `tbil_max`; dates are
  normalized ISO dates or policy-shifted ISO dates;
- exclude DOB, all free text, raw payloads, direct identifiers, source-row
  IDs, source visit IDs, and any non-allowlisted column;
- recursively scan the serialized CSV/Card values for prohibited key names and
  values before finalizing an artifact.

The product records the policy version, policy hash, pseudonym algorithm
`HMAC-SHA256`, and non-secret `key_id`. It derives an ID from UTF-8
`key_id + ":" + canonical_patient_uuid`; stability is limited to that policy
key scope. It never stores the secret, input identifier, or a secret fingerprint.
A missing or empty secret is a build error, not a fallback to an unsafe
deterministic identifier. Secret rotation requires a new policy/key ID and thus
a new product version.

## Build lifecycle

`build_dataset_product` accepts a completed cohort run and a completed quality
run belonging to the same canonicalization run. `dataset_product` is the
immutable logical identity `(slug, version, cohort_run, quality_run, policy
hash)`; `export_attempt` has unique `(dataset_product_id, attempt_number)` and
states `started`, `completed`, or `failed`. Repeating a completed identity
returns its completed attempt; a started attempt conflicts; a failed attempt
requires `retry=true` and creates the next attempt. CSV/Card files are first
written to an attempt-specific temporary path, scanned and hashed, then
atomically renamed before the attempt becomes completed. Failed temporary files
are removed and cannot be downloaded.

The builder reads only canonical/OMOP cohort-scoped data, produces a product
row per eligible canonical patient, and saves a JSON-safe manifest and product
schema snapshot. CSV output uses stable column order and rows sorted by
pseudonymous ID. The physical CSV is written under `exports/` (git-ignored),
and its SHA-256 is persisted. A build records count-only lineage: cohort run,
OMOP run, canonicalization run, quality run, policy version/hash, schema hash,
and export hash.

## Dataset Card and API

The JSON Dataset Card contains the name/version/description/owner, source
systems, patient count, record count (CSV data rows), time coverage (minimum
`first_visit_date` to maximum `last_visit_date`), schema, quality score and
quality report reference, lineage, de-identification status, privacy
policy/version, intended uses, prohibited uses, `created_at`, and `updated_at`.
It contains no source, member, or raw identifiers.

Provide endpoints to list/read products, trigger a build, retrieve a Dataset
Card, retrieve count-only lineage, and download the generated CSV. Missing
resources return 404; incompatible inputs or active/failed duplicate builds
return 409; missing secret, prohibited-field detection, or invalid policy
returns 422. Product API responses must never expose raw IDs, source patient
IDs, source visit IDs, names, phones, or ID numbers.

## Commands and verification

Add `make product` after `make semantics`. It resolves the latest compatible
completed quality/cohort runs, builds the product, and prints the public
product summary. The README documents `PSEUDONYMIZATION_SECRET` and the exact
date/province policy.

PostgreSQL tests cover stable pseudonyms with a test secret/key ID, exact-date
retention, date shifting, age bands, province removal, city/DOB/free-text
removal, recursive prohibited-value scanning, policy/version identity,
compatible-run validation, stable CSV/Card hashes, failed/retry/concurrent
attempt states, atomic artifact visibility, idempotent rebuilds, and
privacy-safe API/Card payloads (including run/source/member IDs). `make test`
remains the required gate.
