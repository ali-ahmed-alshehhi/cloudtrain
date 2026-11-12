# Inference — `inference-service/`

| Owner | Port | Contract |
|---|---|---|
| Majed (Student 8) | 8007 (internal) | `contracts/openapi/inference-service.yaml` |

## What it must do
Load the live model version and answer predictions fast. Inference scales separately from training.

## Endpoints
**Public** (through the gateway, `/api/v1` + path):
- `POST /predict` (multipart image) → 200 prediction

**Own:** `GET /model-info`, `GET /health`, `GET /metrics`.

**Calls (internal):** `GET model-registry:8006/models/{id}/production` — which version to load.

## Reads and writes
- Reads: the model files from bucket `artifacts`.
- No database of its own.

## Acceptance test
After a model version is promoted, `POST /api/v1/predict` with an image returns 200 and a prediction
from that version; `/health` passes before the version takes traffic.
