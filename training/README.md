# Training runtime / worker — `training/`

> **Stand-in.** Abdullah: Replace this stand-in with your real service. Keep the contract. Run `make check` before opening a PR.
>
> What the stand-in already does, and what it does not, is written at the top of `app/main.py`. Its tests in `tests/` show the contract in action: keep them passing (or replace them with better ones).

| Owner | Port | Contract |
|---|---|---|
| Abdullah (Student 4) | 8010 (internal, local development only) | `contracts/openapi/training-worker.yaml`, `contracts/training-job.schema.json` |

Distributed training (DDP) lives in `training/distributed/` (Ahmed + Abdulla).

## What it must do
Run one training job: configurable training scripts for at least two use cases (CIFAR-10 + ResNet-18,
and one tabular dataset), training code in Docker, hyperparameters from the job form, MLflow tracking,
checkpoints and models in S3, evaluation metrics and logs, checkpoint recovery and reproducible runs
(fixed seeds), and the heartbeat and status reports.

## Endpoints
**Public:** none.
**Internal:** `POST /internal/run` (from the Scheduler only, local) → 202. In the cloud the Scheduler
starts an EC2 instance with the job form instead. Plus `GET /health`, `GET /metrics`.

**Calls (internal):**
- `GET dataset-service:8002/internal/datasets/{id}/versions/{v}/download-url` — get the data
- `POST job-service:8003/internal/jobs/{id}/heartbeat` — every `HEARTBEAT_INTERVAL_SECONDS` (default 30);
  stop if the answer says `CANCELLED`
- `POST job-service:8003/internal/jobs/{id}/status` — SUCCEEDED or FAILED when training ends
- MLflow API on `mlflow:5000` — parameters, metrics, the model

## Reads and writes
- Reads: the dataset version from the `datasets` bucket (through the download link).
- Writes: bucket `artifacts` (checkpoints, models) and MLflow runs. Never reads any queue.

## Acceptance test
A cloud training job runs, records its parameters and metrics in MLflow, and stores a reusable model.
