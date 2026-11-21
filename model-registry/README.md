# Model Registry and deployment — `model-registry/`

| Owner | Port | Contract |
|---|---|---|
| Majed (Student 8) | 8006 (internal) | `contracts/openapi/model-registry.yaml` |

Majed also owns `inference-service/`.

## What it does
Registers model versions from MLflow runs, links each one to its MLflow run, training job and
dataset version, puts one version live (promote), and goes back (rollback). A version becomes live
only after Inference loaded it and passed its health check: a failed deployment never replaces the
healthy one.

## Endpoints
**Public** (through the gateway, `/api/v1` + path):
- `POST /models` (from an MLflow run ID, linked to the job and dataset version) → 201
- `GET /models` (`?project_id=` optional; only projects you are a member of)
- `GET /models/{id}/versions`
- `GET /models/{id}/production` (the live version and where its files are)
- `POST /models/{id}/versions/{v}/promote`
- `POST /models/{id}/rollback`

**Internal:** Inference calls `GET /models/{id}/production`. Plus `GET /health` (200 when the database
answers), `GET /metrics`.

## How it works
**Register** (`POST /models`):
1. Membership check: `GET project-service:8001/projects/{id}` with the user's `X-User-Id` (403 / 404).
2. MLflow `runs/get`: the run must exist (else 400 `RUN_NOT_FOUND`) and be `FINISHED`. If the run
   has the tags `project_id`, `job_id`, `dataset_id` or `dataset_version`, they must match the
   request (400 `RUN_MISMATCH`). Its latest metrics are copied into the version.
3. The saved model is found: an MLflow 3 "logged model" of the run, or `model/` in the run's
   artifacts (MLflow 2 style). None → 400 `MODEL_NOT_IN_RUN`.
4. A version is added to MLflow's Model Registry (registered model named like `model-03`), tagged
   with the job, dataset and project.
5. The version is saved in the schema `registry`. `artifact_uri` is the real S3 place of the files
   (`mlflow-artifacts:/…` → `$MLFLOW_ARTIFACTS_DESTINATION/…`), so Inference reads the bucket directly.

Same run twice under one model → 409. `Idempotency-Key` returns the first answer.

**Promote / rollback (the health gate):**
1. `POST inference-service:8007/internal/models/{id}/candidates` with the version's files: Inference
   loads it and runs its health check (one prediction on a test image must give one valid score per
   label).
2. If that fails, or Inference cannot be reached: 503 `DEPLOYMENT_FAILED`, the live version stays,
   and the failed attempt is saved in `deployments`.
3. If it passes: the new live version is saved, MLflow's `production` alias is moved to it, and
   Inference is told to switch now (`POST …/internal/models/{id}/refresh`; otherwise it switches at
   its next check, every `INFERENCE_REFRESH_SECONDS`).

Rollback goes back to the previous live version and passes the same gate. Nothing before → 409.

## Tables (schema `registry`, migrations in `migrations/`)
| Table | What |
|---|---|
| `models` | one row per model (project, name, its MLflow registered-model name) |
| `model_versions` | run ID, MLflow version, job, dataset and version, metrics, artifact place |
| `releases` | every time a version went live; rollback marks the newest one rolled back |
| `deployments` | every promote / rollback attempt and how it ended (failed ones too) |
| `idempotency_keys` | first answers to create requests |

## Settings (`.env`)
`DATABASE_URL` (from `REGISTRY_DATABASE_URL`), `MLFLOW_TRACKING_URI`, `MLFLOW_ARTIFACTS_DESTINATION`,
`PROJECT_SERVICE_URL`, `INFERENCE_SERVICE_URL`, `DEPLOY_TIMEOUT_SECONDS`, `REGISTRY_CALL_TIMEOUT_SECONDS`.

## Run the checks
```bash
bash scripts/test_service.sh model-registry     # unit tests (SQLite and fake services)
make up && .venv/bin/python model-registry/serving_check.py   # end-to-end through the gateway
```
`serving_check.py` uses the small test model in `inference-service/app/fixture_model.py` for its
MLflow runs until the training worker logs real ones.

## For the training worker (Abdullah)
To make a run registrable: log the model with `mlflow.pytorch.log_model(model, name="model", …)` in
the run (see `inference-service/README.md` for the metadata), end the run as `FINISHED`, and set
the run tags `project_id`, `job_id`, `dataset_id`, `dataset_version` from the job form.
