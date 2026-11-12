# MLflow tracking server — `mlflow/`

| Owner | Port | Contract |
|---|---|---|
| Abdullah (Student 4) | 5000 (internal) | the official MLflow REST API (`/api/2.0/mlflow/*`) |

## What it must do
Run the **official MLflow image** (configuration only, no custom code): experiment tracking and the
model registry backend. Runs, parameters and metrics are stored in PostgreSQL; files go to S3.

## Endpoints
**Public (read only, through the gateway):** `/api/v1/experiments/*` is rewritten to `/api/2.0/mlflow/*`.
Only GET, plus POST on paths ending in `/search` (e.g. `/api/v1/experiments/runs/search`).

**Internal:** the full MLflow API, used by the training worker and the Model Registry.

## Reads and writes
- PostgreSQL schema `mlflow` (runs and model registry).
- Bucket `artifacts` (models and run files).

## Acceptance test
A training run appears in MLflow with its parameters and metrics, and the portal can read it through
`GET /api/v1/experiments/...`.
