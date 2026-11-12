# 0005 — LocalStack S3 instead of MinIO on laptops

- **Status:** accepted
- **Date:** 2026-11-12
- **Decided by:** Ali

## Context
The plan used MinIO as the local stand-in for AWS S3. In late 2025 MinIO stopped publishing free Docker
images: `minio/minio` is gone from Docker Hub and `quay.io/minio/minio` now needs a login. It can no
longer run in our `docker-compose.yml`.

Options considered: SeaweedFS (mature, keeps files), RustFS (MinIO look-alike, young project),
LocalStack S3 (already running for SQS).

## Decision
Turn on S3 in the LocalStack container we already run for SQS (`SERVICES: s3,sqs`).
`S3_ENDPOINT=http://localstack:4566`. The buckets `datasets` and `artifacts` are created at start by
`local/localstack/init.sh`. In the cloud nothing changes: real AWS S3, made by Terraform.

## Why
Simplest: one container fewer, the same AWS API the cloud uses, nothing new to learn.

## Trade-offs
LocalStack's free edition keeps everything in memory: **uploaded datasets and saved models are lost
when LocalStack restarts** (keeping them is a paid feature). Locally this means re-uploading test data
after a restart. Job, project and MLflow records in PostgreSQL are kept. The cloud is not affected.

## Upgrade path
If keeping files locally becomes important, add SeaweedFS as a separate `s3` container and point
`S3_ENDPOINT` at it; no service code changes.
