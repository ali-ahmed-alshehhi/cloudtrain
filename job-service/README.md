# Training Jobs service — `job-service/`

| Owner | Port | Contract |
|---|---|---|
| Mariam (Student 3) | 8003 (internal) | `contracts/openapi/job-service.yaml`, `contracts/training-job.schema.json`, `contracts/job-states.md`, `contracts/events/`, `contracts/pricing.yaml` |

It owns the **life** of every training job, from `POST /jobs` to a final status. It does not train
anything: think of a restaurant order desk that takes the order, hands out a ticket number, passes it
to the kitchen and follows it until it is served or sent back.

## What it does

- **Accepts a job** (`POST /jobs` → **202** at once): checks the form, checks that you are a member of
  the project (Projects), that the dataset belongs to that project and the version exists (Datasets),
  saves the job in PostgreSQL as `QUEUED` and puts the full form on the `training-jobs` queue.
  `Idempotency-Key` makes a repeated submit count once.
- **Follows the status steps** of `contracts/job-states.md`, reported by the Scheduler and the worker.
  A step that is not allowed gets **409**; that is how they learn a job was cancelled.
- **Stores every change as an event**: the job's `history`, the alert feed for the portal, and a
  message on the `job-events` queue for monitoring.
- **Never leaves a job RUNNING forever.** A watchdog fails a job whose worker has been silent for
  `HEARTBEAT_TIMEOUT_SECONDS`, or that passed its `max_runtime_minutes`.
- **Retries** a failed job while `retry_limit` allows (event `job.retrying`, `attempt` + 1). When the
  retries are used up, it stays `FAILED` and a failure report goes to `training-jobs-dlq`.
- **Reads `training-jobs-dlq`**: a job the Scheduler could not handle is put back on the queue
  (at most `JOB_DLQ_MAX_REQUEUES` times) instead of waiting in `QUEUED` forever.
- **GPU-hours and cost** per job from `contracts/pricing.yaml`, summed over every attempt
  (a failed attempt still paid for its machine). A running job shows its cost so far.
- **Members only**: listing, reading, cancelling and following a job, and the alert feed, all check
  project membership through the Projects service.

## Endpoints
**Public** (through the gateway at `/api/v1` + path):
- `POST /jobs` → 202 · `GET /jobs?project_id=` · `GET /jobs/{id}` · `POST /jobs/{id}/cancel`
- `GET /jobs/{id}/events` · `GET /jobs/events?after=<event_id>&project_id=&limit=` (alert feed)

**Internal** (never through the gateway):
- `POST /internal/jobs/{id}/status` (Scheduler, worker) · `POST /internal/jobs/{id}/heartbeat` (worker;
  the answer carries the status, `CANCELLED` = stop)

Plus `GET /health` (database and queues reachable) and `GET /metrics`.

## How it is built (a map of `app/`)

| File | What is in it |
|---|---|
| `main.py` | The endpoints. Reads like the contract, top to bottom. |
| `lifecycle.py` | The state machine, retries, the watchdog, and the outbox (see below). |
| `background.py` | The two background loops: the watchdog and the dead-letter reader. |
| `clients.py` | Calls to the Projects and Datasets services. |
| `pricing.py` | GPU-hours and cost. |
| `db.py` + `migrations/` | The tables of schema `jobs` ([docs/database/jobs.md](../docs/database/jobs.md)). |
| `models.py` | The job form, status report and heartbeat, as in the contracts. |
| `settings.py`, `queues.py`, `metrics.py`, `common.py` | Settings, SQS, Prometheus metrics, shared rules. |

**The outbox, in one sentence:** a queue message is saved in the same database transaction as the
change it announces, then sent right after, so a job and its message can never get out of step,
even if SQS is down for a while. Why: [docs/decisions/0006-job-service-design.md](../docs/decisions/0006-job-service-design.md).

## Settings (`.env`)

| Setting | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | — | `JOBS_DATABASE_URL`, schema `jobs` |
| `HEARTBEAT_INTERVAL_SECONDS` / `HEARTBEAT_TIMEOUT_SECONDS` | 30 / 120 | The service refuses to start if the timeout is less than 3 x the interval |
| `JOB_SWEEP_INTERVAL_SECONDS` | 10 | How often the watchdog looks for silent workers and time limits |
| `JOB_OUTBOX_INTERVAL_SECONDS` | 2 | How often unsent queue messages are retried |
| `JOB_DLQ_WAIT_SECONDS` | 20 | Long-polling wait on `training-jobs-dlq` |
| `JOB_DLQ_MAX_REQUEUES` | 3 | How often a job back from the dead-letter queue is queued again |
| `PRICING_FILE` | `/contracts/pricing.yaml` | Prices per machine type |

## Run and test

```bash
make test                         # all unit tests (this folder: 57 tests, ~4 s, no Docker needed)
cd job-service && .venv/bin/python -m pytest -q    # only this service
make up && make e2e               # the walk-through through the gateway
```

The failure-recovery demo (`tests/integration/test_failure_recovery.py`) passes with this service and
the stand-in scheduler and worker. Run it with short settings in `.env`, then `make reset && make up`:
`HEARTBEAT_INTERVAL_SECONDS=2`, `HEARTBEAT_TIMEOUT_SECONDS=6`, `JOB_SWEEP_INTERVAL_SECONDS=2`,
`STANDIN_TRAINING_SECONDS=30`, `SQS_VISIBILITY_TIMEOUT_SECONDS=20`. It takes about one minute.

## Acceptance test
A submitted job enters the queue, is scheduled, runs and reaches a correct final state.
A worker failure never leaves a job `RUNNING` forever.
