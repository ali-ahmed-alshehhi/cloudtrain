# Datasets service — `dataset-service/`

| Owner | Port | Contract |
|---|---|---|
| Faisal (Student 2) | 8002 (internal) | `contracts/openapi/dataset-service.yaml` |

Upload, version and download datasets: check the file format, store a SHA-256 checksum in
PostgreSQL (`datasets` schema), put the file bytes in the `datasets` S3 bucket (LocalStack locally,
real S3 in the cloud), allow **project members only**, record **lineage** (which job used which
version), and give training workers a time-limited download link.

## Endpoints
**Public** (through the gateway, `/api/v1` + path) — each checks membership via Projects:
- `POST /datasets` (multipart upload, checks format, stores checksum) → 201, version 1
- `GET /datasets?project_id=`
- `GET /datasets/{id}`
- `POST /datasets/{id}/versions` → 201
- `GET /datasets/{id}/versions/{v}`
- `GET /datasets/{id}/versions/{v}/download`

**Internal** (never through the gateway):
- `GET /internal/datasets/{id}/versions/{v}/download-url` — presigned S3 URL for the training worker
- `POST /internal/datasets/{id}/versions/{v}/lineage` — body `{"job_id":"job-04"}` records usage
- `GET /internal/datasets/{id}/versions/{v}/lineage` — list jobs that used this version
- Training Jobs calls `GET /datasets/{id}/versions/{v}` to confirm a version exists

Plus `GET /health`, `GET /metrics`.

If object storage is down, mutating/download calls answer **503 SERVICE_UNAVAILABLE** (same idea as a down database).

## Storage
- PostgreSQL schema `datasets` — see `docs/database/datasets.md`
- S3: `s3://datasets/<dataset_id>/v<version>/` (object key `<dataset_id>/v<version>/data`)
- Env: `DATABASE_URL`, `PROJECT_SERVICE_URL`, `S3_ENDPOINT`, `DATASETS_BUCKET`, `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`

## Acceptance test
A user uploads a dataset, creates a new version, and a training job reads the correct version
directly from cloud storage. Non-members get 403. Lineage shows which job used which version.

## Local checks
```bash
cd dataset-service
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
```
