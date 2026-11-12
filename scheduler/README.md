# Scheduler — `scheduler/`

> **Stand-in.** Maitha: Replace this stand-in with your real service. Keep the contract. Run `make check` before opening a PR.
>
> What the stand-in already does, and what it does not, is written at the top of `app/main.py`. Its tests in `tests/` show the contract in action: keep them passing (or replace them with better ones).

| Owner | Port | Contract |
|---|---|---|
| Maitha (Student 7) | 8004 (internal only) | `contracts/openapi/scheduler.yaml`, `contracts/training-job.schema.json` |

## What it must do
Decide where and when each training job runs: CPU or GPU, which machine type, placement and capacity,
quotas and concurrency limits, waiting when capacity is full, starting workers on the infrastructure
from Hamda and Fatma, releasing machines after each job, and watching worker health.

## Endpoints
**Public:** none (internal only). **Own:** `GET /health`, `GET /metrics`.

**Calls (internal):**
- `POST training-worker:8010/internal/run` (local) — or starts an EC2 instance with the job form (cloud)
- `POST job-service:8003/internal/jobs/{id}/status` — SCHEDULED / RUNNING, with machine type and times.
  A 409 answer means the job was cancelled: stop the worker and release the machine.

## Reads and writes
- Queue: the **only reader** of `training-jobs`. Deletes the message once a worker has accepted the job;
  after that the job is protected by the heartbeat lease, not by the queue.
- Writes: PostgreSQL schema `scheduler` (workers, capacity, quotas).

## Acceptance test
CPU and GPU jobs land on the right machines, jobs wait when capacity is full, and machines are
released after use.
