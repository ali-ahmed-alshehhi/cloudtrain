# Scheduler — `scheduler/`

| Owner | Port | Contract |
|---|---|---|
| Maitha (Student 7) | 8004 (internal only) | `contracts/openapi/scheduler.yaml`, `contracts/training-job.schema.json` |

## What it does

Reads the `training-jobs` SQS queue (long polling, 20 s wait) and places each job on a worker.
For every message it picks a machine type based on `gpu_count` (CPU or GPU, see `app/machines.py`),
checks capacity (concurrency limit via `CapacityTracker` in `app/capacity.py`), reports SCHEDULED
to Training Jobs, hands the job to the worker, reports RUNNING, and deletes the queue message.

If the worker is busy (409) it retries every 5 seconds up to the SQS visibility timeout.
If Training Jobs returns 409, the job was cancelled — the slot is released and the message deleted.
If capacity is full the message stays on the queue for the next poll.

## Endpoints

**Public:** none (internal only). **Own:** `GET /health`, `GET /metrics`.

**Calls (internal):**

- `POST training-worker:8010/internal/run` — hand the full job form to the local worker
- `POST job-service:8003/internal/jobs/{id}/status` — SCHEDULED and RUNNING, with `machine_type` and `started_at`

## Configuration (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `ENVIRONMENT` | `local` | `local` or `cloud` — controls machine-type selection |
| `SCHEDULER_MAX_WORKERS` | `1` | Maximum concurrent jobs (capacity limit) |
| `SQS_ENDPOINT` | *(none)* | LocalStack endpoint for local development |
| `TRAINING_JOBS_QUEUE` | `training-jobs` | SQS queue name |
| `JOB_SERVICE_URL` | `http://job-service:8003` | Training Jobs service base URL |
| `TRAINING_WORKER_URL` | `http://training-worker:8010` | Training Worker base URL (fallback for machine types not in TRAINING_WORKER_URLS) |
| `TRAINING_WORKER_URLS` | `{}` | JSON dict mapping machine types to worker pool URLs, e.g. `{"g4dn.xlarge": "http://gpu-lb:8010"}` |
| `SCHEDULER_MAX_GPUS` | *(none)* | Maximum total GPUs the scheduler will commit; unlimited if unset |
| `SQS_VISIBILITY_TIMEOUT_SECONDS` | `300` | Max time to wait for a busy worker |

## Tests

- `tests/test_standin.py` — 8 integration tests (job placement, cancellation, error paths, capacity)
- `tests/test_capacity.py` — 6 unit tests for `CapacityTracker`
- `tests/test_machine.py` — 5 unit tests for machine-type selection

Run: `make test` (Docker) or `pytest scheduler/` from the service directory.

## Queue contract

The scheduler is the **only reader** of `training-jobs`. Once a worker accepts the job, the message
is deleted — after that the job is protected by the heartbeat lease, not the queue.
