# Model Registry and deployment — `model-registry/`

| Owner | Port | Contract |
|---|---|---|
| Majed (Student 8) | 8006 (internal) | `contracts/openapi/model-registry.yaml` |

Majed also owns `inference-service/`.

## What it must do
Register models and versions (MLflow Model Registry), link each model to its MLflow run, job and
dataset version, run the promotion workflow, and roll back. A new version must pass the inference
`/health` check before it takes traffic; a failed deployment never replaces the healthy one.

## Endpoints
**Public** (through the gateway, `/api/v1` + path):
- `POST /models` (from an MLflow run ID, linked to the job and dataset version) → 201
- `GET /models`
- `GET /models/{id}/versions`
- `GET /models/{id}/production` (the live version and where its files are)
- `POST /models/{id}/versions/{v}/promote`
- `POST /models/{id}/rollback`

**Internal:** Inference calls `GET /models/{id}/production`. Plus `GET /health`, `GET /metrics`.

## Reads and writes
- Writes: PostgreSQL schema `registry` (deployments, which version is live, rollback history).
- Calls: MLflow API on `mlflow:5000` (read the run's metrics, register the version).
- Reads: bucket `artifacts`.

## Acceptance test
A trained model is registered, deployed and queried through REST. A failed new deployment never
replaces the healthy one.
