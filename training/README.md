# Training runtime / worker — `training/`

Day 1 provides the real single-job worker foundation and a CPU-capable
CIFAR-10/ResNet-18 path. The API remains the contract-defined asynchronous
worker: `POST /internal/run` returns `202`, a second concurrent job receives
`409 WORKER_BUSY`, and health, metrics, shared errors, request IDs, and JSON
request logs remain enabled.

| Owner | Port | Contract |
|---|---|---|
| Abdullah (Student 4) | 8010 (internal, local development only) | `contracts/openapi/training-worker.yaml`, `contracts/training-job.schema.json` |

Distributed training building blocks live in `training/distributed/` (Ahmed +
Abdulla). Day 1 reuses their dataset, model, and loader helpers. Connecting the
worker lifecycle to multi-process DDP is intentionally a Day 2 task.

## Day 1 execution

For each accepted job the parent runtime:

1. Starts heartbeat supervision independently from dependency retrieval and training.
2. Gets the exact dataset version's URL, downloads it with an HTTP timeout and
   size bound, verifies `checksum_sha256`, and safely extracts zip or tar data
   into temporary storage. Absolute paths, `..`, tar links, and device members
   are rejected.
3. Opens one MLflow run, logs job hyperparameters, and runs ResNet-18 against a
   downloaded archive containing `cifar-10-batches-py`.
4. Logs train/validation loss and accuracy per epoch plus final metrics.
5. Reports exactly one `SUCCEEDED` or `FAILED`. A `CANCELLED` heartbeat stops
   cooperative work without a terminal callback. The job's
   `max_runtime_minutes` is enforced and busy state is always released.

Dataset metadata, download, checksum, archive, MLflow, and training failures are
reported as failed job reasons. Temporary dataset data is removed after the
attempt.

## Endpoints
**Public:** none.
**Internal:** `POST /internal/run` (from the Scheduler only, local) → 202. In the cloud the Scheduler
starts an EC2 instance with the job form instead. Plus `GET /health`, `GET /metrics`.

**Calls (internal):**
- `GET dataset-service:8002/internal/datasets/{id}/versions/{v}/download-url` — get the data
- `POST job-service:8003/internal/jobs/{id}/heartbeat` — every `HEARTBEAT_INTERVAL_SECONDS` (default 30);
  stop if the answer says `CANCELLED`
- `POST job-service:8003/internal/jobs/{id}/status` — SUCCEEDED or FAILED when training ends
- MLflow API on `mlflow:5000` — parameters and metrics

## Configuration

All runtime configuration is through environment variables:

- `JOB_SERVICE_URL` (default `http://job-service:8003`)
- `DATASET_SERVICE_URL` (default `http://dataset-service:8002`)
- `MLFLOW_TRACKING_URI` (required for production execution)
- `MLFLOW_EXPERIMENT_NAME` (default `cloudtrain`)
- `HEARTBEAT_INTERVAL_SECONDS` (default `30`)
- `HTTP_TIMEOUT_SECONDS` (default `30`)
- `DATASET_MAX_BYTES` (default 10 GiB)

Job hyperparameters `epochs`, `batch_size`, and `learning_rate` come directly
from the job form. Optional `momentum`, `num_workers`, and `seed` values are
also honored.

## Reads and writes
- Reads: the dataset version from the `datasets` bucket (through the download link).
- Writes: MLflow run parameters and metrics. Never reads any queue.

## Test

```bash
PYTHON=python3.11 bash scripts/test_service.sh training
```

Unit tests inject tiny trainer and tracker implementations, so they do not
download CIFAR-10 or run ResNet-18. Production dependencies are pinned in
`requirements.txt`, and the image includes both `app/` and `distributed/`.

## Deferred to Day 2

S3 checkpoints and model artifacts, a loadable MLflow model, tabular training,
full reproducibility controls, and worker-level DDP integration are not part of
Day 1. No cloud or GPU execution has been proven by this unit.
