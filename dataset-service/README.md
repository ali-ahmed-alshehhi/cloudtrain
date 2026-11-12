# Datasets service — `dataset-service/`

| Owner | Port | Contract |
|---|---|---|
| Faisal (Student 2) | 8002 (internal) | `contracts/openapi/dataset-service.yaml` |

## What it must do
Upload, version and download datasets: check the file format, store a SHA-256 checksum, keep every
version, allow only project members, record lineage (which job used which version) and an audit trail,
and give training workers a time-limited download link.

## Endpoints
**Public** (through the gateway, `/api/v1` + path):
- `POST /datasets` (multipart upload, checks format, stores checksum) → 201, version 1
- `GET /datasets?project_id=`
- `GET /datasets/{id}`
- `POST /datasets/{id}/versions` → 201
- `GET /datasets/{id}/versions/{v}`
- `GET /datasets/{id}/versions/{v}/download`

**Internal** (never through the gateway):
- `GET /internal/datasets/{id}/versions/{v}/download-url` — for the training worker
- Training Jobs calls `GET /datasets/{id}/versions/{v}` to confirm a version exists

Plus `GET /health`, `GET /metrics`.

## Reads and writes
- Writes: PostgreSQL schema `datasets` (records, versions, checksums, lineage, audit);
  bucket `datasets` (one folder per version: `s3://datasets/<dataset_id>/v<version>/`).
- Calls: Projects service (membership check).

## Acceptance test
A user uploads a dataset, creates a new version, and a training job reads the correct version
directly from cloud storage.
