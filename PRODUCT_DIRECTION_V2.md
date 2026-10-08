# Product Direction v2

## 1. Positioning
**Healthcare High-quality Dataset Factory / 医疗高质量数据集生产平台**

Architecture position:

`HIS / EMR / LIS / PACS -> existing HIP/CDR/Data Lake -> Dataset Factory -> specialty dataset / cohort / AI-ready dataset / data product`

Do not replace the hospital integration platform. Integration manages flow; this product manages dataset production quality, reviewability, traceability, packaging, and repeatability.

## 2. Prototype wedge
Use synthetic liver-disease data only.

Target workflow:

`Synthetic HIS/EMR/LIS -> ingestion -> canonical/specialty model -> mapping -> quality rules -> human review -> cohort -> de-identification -> dataset product pack`

## 3. P0 capabilities
- Existing-platform adapter layer (file + synthetic HIS/EMR/LIS adapters)
- Canonical + liver specialty model, versioned
- Source-to-canonical mapping registry
- Data quality rule engine and quality report
- Field/process lineage: source -> transform -> rule/job/version -> product field
- Cohort rule builder: AND/OR, nested conditions, time windows, preview count, versioning
- Human Review Queue: approve/reject/edit/override with reviewer/time/model-or-rule-version
- RBAC + dataset scope + sensitive field/export permissions
- Audit trail for rule edits, reviews, sensitive views, exports, dataset publication
- Basic de-identification policy engine
- Dataset Product Pack: Dataset Card + schema + quality + lineage + privacy + version + usage policy

## 4. Experimental differentiation
Do not claim these are unique capabilities. Market research found AI schema/mapping and lineage already exist in procurement and competitor products.

The differentiation experiment is **measurable implementation efficiency and control**:
- AI Source->Canonical suggestion with evidence + confidence + Human Review + rollback
- AI quality-rule suggestion with threshold/reason + Human Review
- Unified review workbench across mapping/quality/privacy/product release
- Automatic Dataset Product / Assetization Pack generation
- Vendor-neutral adapter/plugin layer above existing hospital infrastructure

Measure:
- time per 100 fields mapped
- mapping suggestion acceptance rate
- manual edit rate
- rule configuration time
- data issues found
- review workload
- time from source data to versioned Dataset Product

## 5. Prototype benchmark target
These are development targets, not contractual promises:
- 1 disease: liver disease
- 1,000–5,000 synthetic patients
- >=100 meaningful source/canonical fields represented across source tables
- >=30 derived variables/status values
- >=20 executable quality rules
- basic privacy/de-identification policy
- one cohort definition with nested logic and time window
- complete auditable Dataset Product Pack

## 6. Explicit non-goals for prototype
- Real hospital connectivity
- Full PACS/DICOM stack
- Full medical image annotation platform
- Full CTMS / EDC / eCRF platform
- Advanced statistical package replacing R/SPSS/SAS
- Clinical decision support
- Autonomous medical decision making
- Blockchain/trusted data-space infrastructure
- Federated learning/privacy computing platform
- Full enterprise metadata catalog replacement

## 7. Product UX principle
The demo should visibly tell one story:

1. See dirty source data
2. See proposed mappings
3. Review/approve mappings
4. Run quality rules and see before/after quality
5. Build a liver cohort and preview patient count
6. Apply de-identification
7. Publish Dataset v1.0
8. Inspect lineage, audit trail, and generated Dataset Product Pack

If a feature does not strengthen this story, defer it.
