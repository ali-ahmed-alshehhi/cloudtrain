# 0006 — How the Training Jobs service stays correct when things fail

- **Status:** accepted inside `job-service/`; points 6 and 7 are **proposed contract changes**
- **Date:** 2026-11-15
- **Decided by:** Mariam (Student 3)

## Context
The acceptance test says a worker failure must never leave a job `RUNNING` forever. Around that, the
service talks to PostgreSQL, three SQS queues, the Projects and Datasets services, the Scheduler and
the workers, and any of them can be down or late. These are the choices that keep a job's status true.

## Decisions

1. **Transactional outbox for every queue message.** A message for `training-jobs`, `job-events` or
   `training-jobs-dlq` is saved in the `outbox` table in the same transaction as the change it
   announces, then sent right after the commit; the watchdog resends anything left, oldest first.
   *Why:* sending and saving cannot be atomic. The stand-in sent first: a failed save meant the Scheduler
   got a job that did not exist. Saving first without an outbox means a lost send leaves a job in
   `QUEUED` with no message. *Trade-off:* `POST /jobs` answers 202 even when SQS is down (the job waits
   in the outbox); `/health` still reports 503 so the platform shows the problem.

2. **One watchdog, two rules.** Every `JOB_SWEEP_INTERVAL_SECONDS` it fails a `RUNNING` job whose last
   heartbeat (or start, if none came) is older than `HEARTBEAT_TIMEOUT_SECONDS`, or that passed
   `max_runtime_minutes`. The service refuses to start if the timeout is less than 3 x the interval
   (the rule in `contracts/job-states.md`).

3. **A dead worker cannot come back and finish the job.** The worker of an attempt is the one in the
   first heartbeat (or the `RUNNING` report). A status report from another `worker_id` gets 409
   `STALE_WORKER`; its heartbeats are answered but do not keep the attempt alive. *Why:* without this, a
   worker we declared dead (but which was only cut off from the network) could mark attempt 2 as
   `SUCCEEDED` while attempt 2's worker is still training.

4. **Cost counts every attempt.** `gpu_hours` = job's `gpu_count` x hours; `estimated_cost_usd` = the
   machine's hourly price x hours; both summed over all attempts, because a failed attempt still used
   its machine. A machine type missing from `pricing.yaml` counts as 0 and is logged.

5. **Members only, everywhere.** Every public endpoint checks membership with the Projects service. A
   job's dataset must belong to the job's project (`422 DATASET_NOT_IN_PROJECT`); otherwise a member of
   two projects could train one project's job on the other's data. The alert feed answers 403 (not 404)
   for a project you cannot see, because the contract lists no 404 there.

6. **PROPOSED CONTRACT CHANGE: a repeated `SCHEDULED` report is allowed (200, no event).**
   *Found in the live failure-recovery run on 15 Nov:* the retry was reported `SCHEDULED` while the only
   worker was down. The Scheduler kept its queue message; when SQS showed it again, the second
   `SCHEDULED` report got 409, the Scheduler dropped the message, and the job stayed `SCHEDULED` forever.
   The service now answers 200 to `SCHEDULED` → `SCHEDULED` (same attempt, no new event); a cancelled
   job still gets 409. With it, the failure-recovery demo passes. `contracts/job-states.md` needs one
   line for it; the Contract change issue asks Ali and Maitha to agree.

7. **PROPOSED CONTRACT CHANGE (for discussion): a way out of `QUEUED` and `SCHEDULED`.** Today the only
   exits are `RUNNING` and `CANCELLED`. A job whose queue message SQS moved to `training-jobs-dlq`
   is put back on the queue up to `JOB_DLQ_MAX_REQUEUES` times, then logged as an error and left
   `QUEUED` (the user can cancel). A clean answer is a step `QUEUED`/`SCHEDULED` → `FAILED` with the
   reason "could not be scheduled", which would then retry like any failure.

8. **Our own failure reports stay on `training-jobs-dlq`.** This service is the queue's only reader. It
   hides its own reports for 12 hours (the SQS maximum) instead of deleting them, so the queue depth
   stays visible to people and to a CloudWatch alarm; SQS retention removes them later.

## Also worth knowing (for Abdullah and Maitha)
- A worker should stop when the heartbeat answer is anything other than `SCHEDULED` or `RUNNING`, not
  only `CANCELLED`. After a time-limit failure the job is already `QUEUED` for its retry, and the old
  worker should not keep its machine busy.
- `SQS_VISIBILITY_TIMEOUT_SECONDS` decides how fast a job comes back when the Scheduler could not place
  it (300 s by default). For the demo rehearsal, 20 s keeps the failure scenario to about a minute.
