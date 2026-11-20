# Training runtime / worker — `training/`

The worker trains CIFAR-10/ResNet-18 and numeric CSV `tabular_mlp` jobs in
single-process or one-machine DDP mode. The contract-defined asynchronous API
is unchanged: `POST /internal/run` returns `202`, a second concurrent job gets
`409 WORKER_BUSY`, and health, metrics, shared errors, request IDs, and JSON
request logs remain enabled.

| Owner | Port | Contract |
|---|---|---|
| Abdullah (Student 4) | 8010 (internal, local development only) | `contracts/openapi/training-worker.yaml`, `contracts/training-job.schema.json` |

Distributed building blocks remain in `training/distributed/` (Ahmed +
Abdulla).

## Laptop / LocalStack delivery target

For this course delivery, **AWS is simulated on a laptop**: LocalStack stands
in for S3, Compose runs MLflow and the worker on CPU, and no cloud GPU is
required for Student 4 acceptance. Real AWS S3 remains compatible by clearing
`S3_ENDPOINT` and using IAM/env credentials. Use `tabular_mlp` with a small CSV
for the fastest end-to-end laptop path; CIFAR-10/ResNet-18 still works when the
archive contains `cifar-10-batches-py`.

```bash
# from training/, after dependencies are installed
python -m scripts.smoke_local
python -m scripts.evaluate_bundle --bundle /tmp/model-bundle.pt
```
 The worker calls `ddp.launch`, uses a module-level spawn target,
`make_loader`, `set_epoch`, `wrap`, and `unwrap`. Only rank 0 produces
checkpoints, final bundles, and parent-process MLflow records.

## Execution

For each accepted job the parent runtime:

1. Starts heartbeat supervision independently from dependency retrieval and training.
2. Gets the exact dataset version's URL, downloads it with an HTTP timeout and
   size bound, verifies `checksum_sha256`, and safely extracts zip or tar data
   into temporary storage. Absolute paths, `..`, tar links, and device members
   are rejected.
3. Opens one MLflow run and logs the checksum, strategy/world size, software
   versions, job parameters, epoch metrics, and final metrics.
4. Resumes only from an S3 checkpoint whose job, model, dataset checksum,
   hyperparameters, strategy, world size, and checkpoint schema all match.
5. Trains either ResNet-18 from a CIFAR archive containing
   `cifar-10-batches-py`, or a small MLP from exactly one CSV.
6. Writes each immutable checkpoint object before updating the `latest` and
   optional `best` manifests. It writes a reusable final bundle and then the
   `final` manifest.
7. Logs a loadable PyTorch model to MLflow artifact path `model`, with an input
   example and inferred signature.
8. Reports exactly one `SUCCEEDED` or `FAILED`. A `CANCELLED` heartbeat stops
   cooperative work without a terminal callback. The job's
   `max_runtime_minutes` is enforced and busy state is always released.

Python, NumPy, PyTorch, DataLoader workers, splits, and samplers are seeded.
cuDNN benchmarking is disabled and deterministic behavior is requested where
PyTorch supports it. This targets repeatability in the same environment; it
does not promise bitwise equality across hardware, drivers, or PyTorch builds.

## Tabular CSV

`model: tabular_mlp` expects one CSV with finite numeric features and a
categorical target. `target_column` defaults to `diagnosis`. The seeded split is
stratified, and means/scales are learned only from training rows. Metrics are
cross-entropy loss, accuracy, and macro F1. The final bundle contains weights,
architecture, feature order, train-only standardization statistics, target
name, class labels, and input schema. `app.tabular.load_model_bundle` rebuilds
the model for inference.

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
- `ARTIFACTS_BUCKET` (required)
- `S3_ENDPOINT` (set for LocalStack; omit/empty for AWS)
- `AWS_REGION` (default `us-east-1`; credentials use the normal boto3 IAM/env chain)
- `HEARTBEAT_INTERVAL_SECONDS` (default `30`)
- `HTTP_TIMEOUT_SECONDS` (default `30`)
- `DATASET_MAX_BYTES` (default 10 GiB)
- `TRAINING_SHM_SIZE` (Compose shared memory, default 2 GiB in `.env.example`)

Job hyperparameters `epochs`, `batch_size`, and `learning_rate` come from the
job form. Optional common values are `momentum`, `num_workers`, and `seed`.
Tabular jobs also accept `target_column` (default `diagnosis`), `hidden_size`
(default `32`), and `validation_fraction` (default `0.2`).

## Reads and writes
- Reads: the dataset through its versioned download link and compatible
  `latest` checkpoint manifests from the artifacts bucket.
- Writes: immutable checkpoints, `latest`/`best`/`final` manifests, final model
  bundles, and MLflow parameters, tags, metrics, signature, and model.
- Never reads a queue.

## Test

```bash
PYTHON=python3.11 bash scripts/test_service.sh training
```

Storage and tracking clients are injectable; unit tests need neither AWS nor a
live MLflow server. The tiny CSV fixture keeps the tabular path fast. CPU DDP
checks use Gloo where the installed PyTorch/platform supports process spawning.
Production dependencies pin PyTorch/torchvision 2.9.1/0.24.1 and MLflow 3.18.0.

The unit suite uses injectable fakes. Laptop acceptance is `scripts.smoke_local`
plus Compose/LocalStack (`make up` then `make e2e`). CUDA, multi-GPU, and
cross-hardware bitwise reproducibility are out of scope for Student 4.
