# Inference — `inference-service/`

| Owner | Port | Contract |
|---|---|---|
| Majed (Student 8) | 8007 (internal) | `contracts/openapi/inference-service.yaml` |

## What it does
Serves predictions from the live model version. It asks the Model Registry which version is live,
reads that version's files from the `artifacts` bucket, loads them with MLflow and PyTorch (CPU),
and answers `POST /predict` with the most likely labels for an image. Inference scales separately
from training and does not call MLflow while serving.

## Endpoints
**Public** (through the gateway, `/api/v1` + path):
- `POST /predict` (multipart: `file` = PNG or JPEG; optional `model_id`, default
  `INFERENCE_DEFAULT_MODEL_ID`) → 200 `{model_id, version, predictions: [{label, score}]}`

**Own:** `GET /model-info` (the loaded version of the default model), `GET /health`, `GET /metrics`.

**Internal** (called by the Model Registry; the gateway refuses `/internal/` paths):
- `POST /internal/models/{id}/candidates` — load a version and run its health check BEFORE it may go
  live → 200 healthy, or 503 `MODEL_UNHEALTHY` with the reason
- `POST /internal/models/{id}/refresh` — the live version changed: switch now

**Calls:** `GET model-registry:8006/models/{id}/production`.

## Where it runs: "on AWS" here means the AWS Emulator
Our "AWS" is the AWS Emulator, not an AWS account ([decision 0011](../docs/decisions/0011-aws-emulator-instead-of-aws-account.md)).
The emulator does not run real containers on ECS, so **this service does not serve traffic on real
AWS**. Two separate things are true:

1. **In Terraform:** `infrastructure/modules/application-services` defines an ECS service and task
   definition for `inference-service` (image from the ECR repository, port 8007, the shared service
   environment, and a `/health` container check). It is meant to apply cleanly on the emulator; that
   proves the definition is valid, not that predictions are served from it.
2. **In the local stack:** the prediction API really runs in `docker compose` (`make up`), behind the
   gateway. This is what the portal calls.

### Call the prediction API (local stack, through the gateway)
```bash
curl -X POST http://localhost:5810/api/v1/predict \
  -H "Authorization: Bearer $DEV_AUTH_TOKEN" \
  -F "file=@cat.png" \
  -F "model_id=model-01"
```
- URL: `http://localhost:5810/api/v1/predict` (the gateway strips `/api/v1`; port 8007 is not reachable from outside).
- Header: `Authorization: Bearer <token>`. Locally, `DEV_AUTH_TOKEN` from `.env`; with the real login, a Cognito ID token.
- Body: `multipart/form-data` with `file` (PNG or JPEG, up to 10 MB) and optionally `model_id`
  (default `INFERENCE_DEFAULT_MODEL_ID`, `model-01`). It takes an image, not a row of features.
- Answer, `200`: the live model's `INFERENCE_TOP_K` (3) most likely labels, best first:
  ```json
  {"model_id": "model-01", "version": 1,
   "predictions": [{"label": "cat", "score": 0.91}, {"label": "dog", "score": 0.05}, {"label": "deer", "score": 0.02}]}
  ```
  (the scores above are only an example of the shape).
- `503 NO_MODEL_LOADED` until a version of that model has been promoted (see the Model Registry README); `400` for an unknown `model_id` or a file that is not an image.

## The health check, and why a bad version never takes traffic
A version is served only after it loaded and one prediction on a fixed test image gave exactly one
finite score per label. A candidate is checked before the registry promotes it. If the registry
ever names a version that fails here (e.g. another copy of this service checked it), this copy
keeps serving the version it has. If the registry is down, the loaded version keeps serving.
`GET /health` is 503 only when the loaded default model fails its check; with no model yet it is 200
(the service is up; `/predict` answers 503 `NO_MODEL_LOADED`).
See model-registry README “Issue #48 — done on main” for the gate, tests, and walk-through pointers.

## Which models work
Any model saved with `mlflow.pytorch.log_model` (MLflow's `pickle` format, or `pt2` exported with a
batch of one) that takes a `(1, 3, size, size)` image tensor and returns one score per class —
e.g. the worker's ResNet-18 for CIFAR-10 (`torchvision.models.get_model("resnet18", num_classes=10)`).
How to prepare images comes from the model's MLflow metadata; the defaults are CIFAR-10's:

```python
mlflow.pytorch.log_model(
    model,
    name="model",
    serialization_format="pickle",
    metadata={
        "labels": ["airplane", "automobile", "bird", "cat", "deer", "dog", "frog", "horse", "ship", "truck"],
        "image_size": 32,  # images are resized to 32 x 32
        "normalize_mean": [0.4914, 0.4822, 0.4465],  # the same normalisation as in training
        "normalize_std": [0.2470, 0.2435, 0.2616],
    },
)
```

Model files are pickles that run code when loaded: only versions registered by the Model Registry
from our own MLflow runs are loaded, from our own bucket.

## The test model (until the worker logs real ones)
`app/fixture_model.py` trains a small CNN for a few seconds on synthetic CIFAR-shaped images and
logs it as a normal MLflow run (with job and dataset tags), so registration, promotion and
prediction run for real today:
```bash
docker compose exec inference-service python -m app.fixture_model \
  --project-id project-01 --job-id job-01 --dataset-id dataset-01 --dataset-version 1   # prints the run ID
```
`--broken` logs a model that fails the health check, to show a failed deployment.

## Settings (`.env`)
`MODEL_REGISTRY_URL`, `S3_ENDPOINT` (LocalStack locally, empty on AWS), `AWS_REGION`,
`INFERENCE_DEFAULT_MODEL_ID`, `INFERENCE_REFRESH_SECONDS`, `INFERENCE_TOP_K`, `INFERENCE_MAX_IMAGE_BYTES`.

## Run the checks
```bash
bash scripts/test_service.sh inference-service   # unit tests: real models (test CNN, ResNet-18), fake registry
```
