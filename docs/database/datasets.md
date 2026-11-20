# Schema `datasets` — the Datasets service

**Owner:** Faisal (Student 2). Only the Datasets service reads or writes this schema; other services call its API.
**Holds:** dataset records, versions, checksums, lineage, and an audit record of uploads and downloads.

The schema and its database user `datasets` are created by the database setup (locally the postgres
start-up script, in the cloud the infrastructure setup). The service's user owns the schema but cannot
create new schemas (least privilege).

## Tables

| Table | What one row is | Key columns |
|---|---|---|
| `datasets` | One dataset | `id` (shown outside as `dataset-01`), `project_id`, `name`, `description`, `format`, `created_by`, `created_at` |
| `versions` | One version of one dataset | `id`; (`dataset_id`, `number`) unique; `checksum_sha256`, `size_bytes`, `storage_uri`, `object_key`, `note`, `created_by`, `created_at` |
| `lineage` | One job that used one version | `id`; (`job_id`, `dataset_id`, `version`) unique; `recorded_at` |
| `audit_events` | One upload, new version, download or download link | `id`; `action`, `dataset_id`, `version`, `actor`, `request_id`, `at` |
| `idempotency_keys` | The first answer to a create request sent with an `Idempotency-Key` | (`user_id`, `key`) unique; `request_fingerprint`, `status_code`, `response_body`, `created_at` |
| `alembic_version` | Which migration has been applied (kept by Alembic) | `version_num` |

## Relationships
```mermaid
erDiagram
  datasets ||--o{ versions : "has"
  datasets ||--o{ lineage : "used_by"
  datasets ||--o{ audit_events : "audited_by"
  datasets {
    int id PK
    string project_id
    string name
    string description
    string format
    string created_by
    timestamptz created_at
  }
  versions {
    int id PK
    int dataset_id FK
    int number
    string checksum_sha256
    bigint size_bytes
    string storage_uri
    string object_key
    string note
    string created_by
    timestamptz created_at
  }
  lineage {
    int id PK
    int dataset_id FK
    int version
    string job_id
    timestamptz recorded_at
  }
  audit_events {
    int id PK
    string action
    int dataset_id FK
    int version
    string actor
    string request_id
    timestamptz at
  }
  idempotency_keys {
    string user_id PK
    string key PK
    string request_fingerprint
    int status_code
    json response_body
    timestamptz created_at
  }
```

## Indexes and constraints
- `ix_datasets_project_id`: fast list by project (`GET /datasets?project_id=`).
- `uq_versions_dataset_number`: a dataset cannot have two rows with the same version number.
- `uq_lineage_job_dataset_version`: the same job is recorded once per version.
- `ix_lineage_dataset_version`: list lineage for one version quickly.
- `ix_audit_events_dataset`: list the audit of one dataset quickly, in order.
- `audit_events` rows are only ever added, never changed or deleted. A row is saved in the same
  transaction as the upload it describes, so a failed upload leaves no audit row.
- `idempotency_keys` primary key (`user_id`, `key`): two identical create requests can never both be saved.
- All times are stored in UTC (`timestamptz`).

## Object storage
Files live in the datasets bucket (`datasets` locally; a globally unique name on AWS, from
`DATASETS_BUCKET`). Version *n* of `dataset-07` is stored as key `dataset-07/vN/data` and reported as
`storage_uri = s3://<bucket>/dataset-07/vN/`.

## Migrations
Migrations are in `dataset-service/migrations/versions/`. The container applies them on start
(`alembic upgrade head`) before serving requests. To add one:
```bash
cd dataset-service
DATABASE_URL=postgresql+psycopg://... .venv/bin/alembic revision -m "what changes"
```
