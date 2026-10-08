# Architecture

## Logical architecture

```text
┌───────────────────────────────────────────────┐
│ Synthetic Hospital Sources                    │
│ HIS             EMR              LIS          │
└───────┬──────────┬────────────────┬───────────┘
        │          │                │
        └──────────┴────────┬───────┘
                           ▼
                  Raw Ingestion Layer
                           │
                           ▼
                 Canonical Healthcare Model
                 - IDs / dates / codes
                 - lab-name normalization
                 - unit normalization
                           │
             ┌─────────────┴─────────────┐
             ▼                           ▼
      Data Quality Engine        Lineage / Metadata
             │                           │
             ▼                           │
       OMOP-Compatible Layer             │
             │                           │
             ▼                           │
       Liver Cohort Builder              │
             │                           │
             ▼                           │
      De-identification Engine           │
             │                           │
             └─────────────┬─────────────┘
                           ▼
                  Dataset Product Layer
             Dataset Card / Quality / Schema
                   Usage / Version / Export
                           │
                           ▼
                       FastAPI
```

## Physical components

### app/api
FastAPI routes and API contracts.

### app/domain
Healthcare-specific domain models independent of persistence.

### app/db
SQLAlchemy models, sessions, repositories, migrations.

### app/synthetic
Synthetic hospital data generation.

### app/ingestion
Source ingestion and raw-zone loading.

### app/canonical
Normalization / standardization transforms.

### app/quality
Rules, execution engine, scoring, reports.

### app/omop
OMOP-compatible mapping.

### app/cohorts
Versioned cohort definitions and builders.

### app/privacy
De-identification policies and transforms.

### app/lineage
Lineage event creation / retrieval.

### app/products
Dataset Card, versioning, export.

## Storage zones

Use separate schemas or clearly separated tables:

- `his_src`
- `emr_src`
- `lis_src`
- `raw`
- `canonical`
- `omop`
- `product`
- `governance`

Avoid destructive overwrites between zones.

## Integration boundary

Later adapters may connect:
- qData
- DataHub
- HAPI FHIR
- OpenHIM
- ARX
- Orthanc

Core pipeline should not depend on any of them for basic operation.
