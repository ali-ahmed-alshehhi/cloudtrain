# job-events-monitor (owners: Hilal + Adel, Student 10)

The **only reader** of the SQS queue `job-events` (`docs/ARCHITECTURE.md`, decision 0002). Training Jobs
puts one message there for every job status change (`contracts/events/job-event.schema.json`).
This service turns them into metrics for the dashboards. Proposal and agreement: **#109**.

## What it measures
| Metric (`GET /metrics`) | Meaning |
|---|---|
| `cloudtrain_job_events_total{event_type}` | events read, by type (`job.queued`, `job.running`, ...) |
| `cloudtrain_job_retries_total` | `job.retrying` events |
| `cloudtrain_job_queue_wait_seconds` (histogram) | per attempt: QUEUED (`job.queued` or `job.retrying`) → RUNNING |
| `cloudtrain_job_run_seconds{result}` (histogram) | per attempt: RUNNING → SUCCEEDED / FAILED / CANCELLED |
| `cloudtrain_job_event_lag_seconds` (histogram) | when we read the event minus `occurred_at` |
| `cloudtrain_job_events_duplicate_total` | events ignored because their `event_id` was already handled |
| `cloudtrain_job_events_invalid_total{reason}` | messages that are not a valid event: `not_json`, `schema`, `bad_time` |
| `cloudtrain_job_events_poll_errors_total` | failed reads or deletes on the queue |
| `cloudtrain_job_events_last_poll_timestamp_seconds` | last successful read (Unix time) |
| `cloudtrain_job_attempts_tracked` | attempts whose timings are kept in memory |

Plus the shared request metrics (`job_events_monitor_requests_total`, ...). On AWS the same numbers are
also written as **CloudWatch Embedded Metric Format** log lines (namespace `CloudTrain`), so they become
CloudWatch metrics with log permissions only. Turn off with `JOB_EVENTS_EMF=false`.

## How it behaves
- The queue is **at least once** and may reorder: an `event_id` seen before is ignored, and an attempt is
  timed whichever order its events arrive in. Each duration is recorded once.
- Valid, duplicate and invalid messages are **deleted** after they are counted (an invalid message would
  otherwise come back forever; it is counted and logged as a warning). If the monitor's own code fails on a
  message, the message is **kept** and SQS shows it again.
- Queue unreachable: retries after 1, 2, 4 ... up to 30 seconds.
- `GET /health` is **200** only if the queue was read successfully in the last 120 s
  (`JOB_EVENTS_HEALTHY_WITHIN_SECONDS`), otherwise 503 in the shared error format.
- **Limitation:** timings live in memory. A restart forgets attempts in flight (their durations are not
  measured); counts are not affected. Memory is bounded (50 000 event ids, 10 000 attempts, 24 h).

## Settings (environment variables)
`JOB_EVENTS_QUEUE` (default `job-events`), `SQS_ENDPOINT` (LocalStack locally; empty on AWS), `AWS_REGION`,
`JOB_EVENTS_WAIT_SECONDS` (long poll, default 20), `JOB_EVENT_SCHEMA`, `JOB_EVENTS_EMF`,
`JOB_EVENTS_HEALTHY_WITHIN_SECONDS`. AWS permissions needed, on `job-events` only: `sqs:GetQueueUrl`,
`sqs:ReceiveMessage`, `sqs:DeleteMessage`.

## Run the tests
```bash
cd monitoring/job-events-monitor
python3.11 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```
The tests use **FIXTURE** events (made up, checked against the contract), a fake SQS (`moto`) for the real
boto3 calls, and `tests/fixtures/FIXTURE-recorded-from-job-service.json`: what Training Jobs actually put
on the queue when its own test harness ran (fake clock, not real training or cloud results).

## Not done yet (waiting for #109)
Adding it to `docker-compose.yml`, `contracts/ports.md`, `.env.example`, the `make test` list and CI
(`scripts/changed_services.sh`) are shared-file changes: they come after Ali agrees on #109.
