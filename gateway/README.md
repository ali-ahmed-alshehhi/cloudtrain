# API Gateway — `gateway/`

| Owner | Port | Contract |
|---|---|---|
| Ali (Student 1) | **5810 (published)** | `contracts/openapi/gateway.yaml`, routes in `gateway/app/routes.yaml` |

## What it must do
The one front door. All API traffic from the browser and the portal enters here and nowhere else.
On every request it:
- checks the login token (JWT); local dev mode (`AUTH_MODE=dev`) accepts the fixed token from `.env`
- adds `X-User-Id` and `X-Request-Id` (creates a request ID if none came in)
- forwards to the right service with a 10-second timeout (uploads: 300 seconds)
- answers **503** in the shared error format if that service is down or too slow
- answers **404** for any path containing `/internal/`
- allows CORS from `http://localhost:3000` and `DEPLOYED_PORTAL_URL`
- writes one JSON log line per request

## Endpoints
**Its own:** `GET /health`, `GET /metrics`.

**Forwarded** (from `routes.yaml`):

| Public path | Forwards to | Methods |
|---|---|---|
| `/api/v1/users/me`, `/api/v1/projects/*` | `project-service:8001` (strip `/api/v1`) | all |
| `/api/v1/datasets/*` | `dataset-service:8002` (strip `/api/v1`) | all |
| `/api/v1/jobs/*` | `job-service:8003` (strip `/api/v1`) | all |
| `/api/v1/experiments/*` | `mlflow:5000/api/2.0/mlflow/*` (rewrite) | GET, and POST only on paths ending in `/search` |
| `/api/v1/models/*` | `model-registry:8006` (strip `/api/v1`) | all |
| `/api/v1/predict/*` | `inference-service:8007` (strip `/api/v1`) | all |

**Internal:** none.

## Reads and writes
No database, no queue. Reads only its route table and environment variables.

## Acceptance test
A logged-in user creates a project through the gateway, uploads a dataset (Faisal) and submits a
training job (Mariam). Unit tests cover: every route, the MLflow rewrite, POST blocked on experiments
except `/search`, 401 without a token, 503 when a service is down, `/internal/` blocked,
request ID passed through, and the error format.
