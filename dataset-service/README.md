# Datasets service — `dataset-service/`

| Owner | Port | Contract |
|---|---|---|
| Faisal (Student 2) | 8002 (internal) | `contracts/openapi/dataset-service.yaml` |

Upload, version and download datasets: check the file format, store a SHA-256 checksum in
PostgreSQL (`datasets` schema), put the file bytes in the `datasets` S3 bucket (LocalStack locally,
real S3 in the cloud), allow **project members only**, record **lineage** (which job used which
version), keep an **audit record** of every upload, new version, download and download link, and give
training workers a time-limited download link.

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
- `GET /internal/datasets/{id}/audit` — every upload, new version, download and download link for one
  dataset, oldest first: `{"items":[{"dataset_id","version","action","actor","request_id","at"}]}`.
  `action` is `upload`, `new_version`, `download` or `download_url`; `actor` is the user id, or
  `internal` when a worker asks for a link. Refused or failed requests are not recorded.
- Training Jobs calls `GET /datasets/{id}/versions/{v}` to confirm a version exists

Plus `GET /health`, `GET /metrics`.

If object storage is down, mutating/download calls answer **503 SERVICE_UNAVAILABLE** (same idea as a down database).
If storage is up but a version's file is gone (for example LocalStack was restarted, since it keeps
files in memory), the download answers **404 DATASET_FILE_MISSING** instead, so the message points to
the real cause.

## Storage
- PostgreSQL schema `datasets` — see `docs/database/datasets.md`
- S3: `s3://<bucket>/<dataset_id>/v<version>/` (object key `<dataset_id>/v<version>/data`). The bucket
  is `datasets` locally; on AWS it is the unique name in `DATASETS_BUCKET`, and `storage_uri` uses it.
- Env: `DATABASE_URL`, `PROJECT_SERVICE_URL`, `S3_ENDPOINT`, `DATASETS_BUCKET`, `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`

## Running on AWS
Nothing in the code changes between a laptop and AWS; only the settings do. The ECS task
(`infrastructure/modules/application-services`) sets them:

| Setting | Laptop (`make up`) | AWS (ECS) |
|---|---|---|
| `S3_ENDPOINT` | `http://localstack:4566` | **not set**, so real S3 is used |
| `DATASETS_BUCKET` | `datasets` | Terraform output `datasets_bucket` (globally unique) |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | LocalStack test keys | **not set**: the ECS task role `dataset-service` gives S3 access (read/write the datasets bucket only) |
| `AWS_REGION` | `us-east-1` | the region from Terraform |
| `DATABASE_URL` | local PostgreSQL | Secrets Manager `cloudtrain/<env>/database/datasets` (written by `infrastructure/scripts/bootstrap-schemas.sh`, with `sslmode=require`) |

On start the container runs `alembic upgrade head`, so the tables (including `audit_events`) are
created in the `datasets` schema on RDS. Download links for workers are signed with the task role and
expire after 15 minutes; the worker's own role can also read the bucket.

## Acceptance test
A user uploads a dataset, creates a new version, and a training job reads the correct version
directly from cloud storage. Non-members get 403. Lineage shows which job used which version, and
the audit list shows who uploaded and downloaded each version.

## Local checks
```bash
cd dataset-service
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
```
