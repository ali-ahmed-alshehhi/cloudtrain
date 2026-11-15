# Schema `jobs` — the Training Jobs service

**Owner:** Mariam (Student 3). Only the Training Jobs service reads or writes this schema; other services call its API.
**Holds:** jobs, status history, events (for the alert feed), retries, cost.

## Tables

| Table | What one row is | Key columns |
|---|---|---|
| `jobs` | One training job: its form and where it stands now | `id` (→ `job-104`), `project_id`, `submitted_by`, `spec` (the form, JSON), `status`, `attempt`, `machine_type`, `worker_id`, `started_at`, `finished_at`, `last_heartbeat_at`, `dlq_requeues` |
| `attempts` | One run of a job on one machine. A retry is a new attempt. | (`job_id`, `number`), `machine_type`, `worker_id`, `started_at`, `finished_at`, `outcome`, `reason` |
| `events` | One status change. The job's `history` and the alert feed are both read from here. | `id` (→ `event-1001`), `job_id`, `project_id`, `event_type`, `occurred_at`, `data` (JSON, as `contracts/events/job-event.schema.json`) |
| `outbox` | One queue message waiting to be sent, or already sent | `id`, `queue`, `body` (JSON), `sent_at` (empty = not sent yet), `tries`, `last_error` |
| `idempotency_keys` | The first answer to a `POST /jobs` sent with an `Idempotency-Key` | (`user_id`, `key`), `request_fingerprint`, `job_id`, `response_body` |

Why `attempts` is its own table: GPU-hours and cost add up **every** attempt, because a failed
attempt still kept (and paid for) its machine. `jobs.started_at` / `finished_at` show only the
current attempt.

Why `events` is the history: one source of truth. A status change writes one event row; the job's
`history`, `GET /jobs/{id}/events` and the alert feed are three views of the same rows, so they can
never disagree.

## Relationships

```
jobs 1 ──< attempts           (attempts.job_id → jobs.id)
jobs 1 ──< events             (events.job_id → jobs.id)
jobs 1 ──< idempotency_keys   (idempotency_keys.job_id → jobs.id)
outbox                        (no foreign key: a message is a copy, sent and then kept for audit)
```

## Indexes and constraints

| Index / key | Why |
|---|---|
| `ix_jobs_project_id` | `GET /jobs?project_id=` |
| `ix_jobs_status` | The watchdog asks "every RUNNING job" every few seconds |
| `ix_events_project_id_id` (`project_id`, `id`) | The alert feed: "events of my projects after event N", oldest first |
| `ix_events_job_id` | `GET /jobs/{id}/events` |
| `ix_outbox_sent_at` | "Messages not sent yet" |
| primary key (`user_id`, `key`) on `idempotency_keys` | Two identical submits at the same moment: the database lets only one win, the other gets the same answer |

Changing a job takes a row lock (`SELECT ... FOR UPDATE`); the watchdog and the outbox use
`SKIP LOCKED`, so several copies of the service can run side by side without changing the same job twice.

## Migrations

Alembic, in `job-service/migrations/`. The container runs `alembic upgrade head` before it starts.
The schema `jobs` and the user `jobs` are created by the database setup (locally
`local/postgres/init.sh`, in the cloud Terraform); the service user cannot create schemas.

```bash
cd job-service
# after changing app/db.py, write the next file in migrations/versions/ (0002_..., down_revision = "0001")
DATABASE_URL=postgresql+psycopg://jobs:jobs-local-only@localhost:5432/cloudtrain .venv/bin/alembic upgrade head
```
