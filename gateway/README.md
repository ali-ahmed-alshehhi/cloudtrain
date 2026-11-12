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

## Files

| File | What it does |
|---|---|
| `app/main.py` | Builds the app; the step-by-step handling of every request |
| `app/routes.yaml` | The route table (a contract: change it only through a Contract change issue) |
| `app/routing.py` | Reads `routes.yaml`, finds the route, rewrites the path, blocks `/internal/` |
| `app/auth.py` | `verify_token()` — the one login check (dev token locally, real JWT in the cloud) |
| `app/proxy.py` | Forwards the request (streamed) and turns "service down / too slow" into 503 |
| `app/errors.py` | The shared error format |
| `app/logs.py`, `app/metrics.py` | JSON log lines and Prometheus metrics |
| `app/config.py` | Settings from environment variables; refuses the dev token outside a laptop |

## Run the tests
```bash
cd gateway
python3.11 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

## Acceptance test
A logged-in user creates a project through the gateway, uploads a dataset (Faisal) and submits a
training job (Mariam). Unit tests cover: every route, the MLflow rewrite, POST blocked on experiments
except `/search`, 401 without a token, 503 when a service is down, `/internal/` blocked,
request ID passed through, and the error format.
