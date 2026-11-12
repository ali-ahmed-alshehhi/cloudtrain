# Training Jobs service — `job-service/`

> **Stand-in.** Mariam: Replace this stand-in with your real service. Keep the contract. Run `make check` before opening a PR.
>
> What the stand-in already does, and what it does not, is written at the top of `app/main.py`. Its tests in `tests/` show the contract in action: keep them passing (or replace them with better ones).

| Owner | Port | Contract |
|---|---|---|
| Mariam (Student 3) | 8003 (internal) | `contracts/openapi/job-service.yaml`, `contracts/training-job.schema.json`, `contracts/job-states.md`, `contracts/events/` |

## What it must do
Owns the job **lifecycle** (not the training algorithms): accept and validate the job form, save it,
queue it, track its status, cancel, retry, time limits, dead-worker detection by missing heartbeats,
job events and the alert feed, and the GPU-hours and cost of each job.

## Endpoints
**Public** (through the gateway, `/api/v1` + path):
- `POST /jobs` → **202** with the job in `QUEUED` (honours `Idempotency-Key`)
- `GET /jobs?project_id=`
- `GET /jobs/{id}` (status, history, `machine_type`, `gpu_hours`, `estimated_cost_usd`)
- `POST /jobs/{id}/cancel`
- `GET /jobs/{id}/events`
- `GET /jobs/events?after=<event_id>&project_id=` — the alert feed (portal calls it every 5–10 s with back-off)

**Internal** (never through the gateway):
- `POST /internal/jobs/{id}/status` — from the Scheduler and the worker
- `POST /internal/jobs/{id}/heartbeat` — from the worker, every `HEARTBEAT_INTERVAL_SECONDS`

Plus `GET /health`, `GET /metrics`.

## Reads and writes
- Writes: PostgreSQL schema `jobs` (jobs, history, events, retries, cost).
- Queues: **writes** `training-jobs` (the full form) and `job-events` (every status change);
  **reads** `training-jobs-dlq` (failure reports).
- Calls: Datasets service (does the dataset version exist?), Projects service (membership).
- Reads `contracts/pricing.yaml` for cost.

## Acceptance test
A submitted job enters the queue, is scheduled, runs and reaches a correct final state.
A worker failure never leaves a job `RUNNING` forever.
