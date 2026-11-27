# Test H: a worker killed in the middle of a job (raw results)

**Measured:** Sun 22 Nov 2026, about 15:15 (UTC+4), by Adel on the laptop in section 0 of `EVALUATION.md`.
**Versions:** `main` at `1bb2326`. **Settings:** the short heartbeat settings of
`tests/integration/test_failure_recovery.py` (#145), put in `.env` for this test only and taken out afterwards:
`HEARTBEAT_INTERVAL_SECONDS=2`, `HEARTBEAT_TIMEOUT_SECONDS=6`, `JOB_SWEEP_INTERVAL_SECONDS=2`,
`SQS_VISIBILITY_TIMEOUT_SECONDS=20` (defaults: 30, 120, 10, 300). With them, `make e2e` ran Mariam's
failure-recovery test too: 26 passed, 3 skipped.

## Commands

```bash
cp .env /tmp/env.backup
sed -i '' -e 's/^HEARTBEAT_INTERVAL_SECONDS=.*/HEARTBEAT_INTERVAL_SECONDS=2/' \
  -e 's/^HEARTBEAT_TIMEOUT_SECONDS=.*/HEARTBEAT_TIMEOUT_SECONDS=6/' \
  -e 's/^JOB_SWEEP_INTERVAL_SECONDS=.*/JOB_SWEEP_INTERVAL_SECONDS=2/' \
  -e 's/^SQS_VISIBILITY_TIMEOUT_SECONDS=.*/SQS_VISIBILITY_TIMEOUT_SECONDS=20/' .env
make down && make up && make e2e
export DEV_AUTH_TOKEN=$(grep '^DEV_AUTH_TOKEN=' .env | cut -d= -f2)
python3 docs/evaluation/recovery.py 3
cp /tmp/env.backup .env && make down && make up      # back to the normal settings
```

[`recovery.py`](recovery.py), per run: submit a 300-epoch job, wait until RUNNING, wait 3 s, kill the worker
(`docker compose kill training-worker`), wait for `job.retrying`, start the worker again
(`docker compose start training-worker`), wait for the end. Times are from the kill (laptop clock) to each
event's `occurred_at` (Docker's clock; Test E found the two within 0.03 s).

## Output

```
HEARTBEAT_TIMEOUT_SECONDS=6, HEARTBEAT_INTERVAL_SECONDS=2, JOB_SWEEP_INTERVAL_SECONDS=2, SQS_VISIBILITY_TIMEOUT_SECONDS=20; 3 runs

job-35: SUCCEEDED, attempt 2; worker started again 6.3 s after the kill
  job.queued     attempt 1     -3.2 s  
  job.scheduled  attempt 1     -3.2 s  
  job.running    attempt 1     -3.2 s  
  job.failed     attempt 1     +6.1 s  no heartbeat for 7 seconds (worker-ca2e8e39a03c stopped answ
  job.retrying   attempt 2     +6.1 s  retry 1 of 2
  job.scheduled  attempt 2     +6.1 s  
  job.running    attempt 2    +26.6 s  
  job.succeeded  attempt 2    +43.9 s  

job-36: SUCCEEDED, attempt 2; worker started again 5.0 s after the kill
  job.queued     attempt 1     -3.2 s  
  job.scheduled  attempt 1     -3.2 s  
  job.running    attempt 1     -3.2 s  
  job.failed     attempt 1     +4.9 s  no heartbeat for 6 seconds (worker-ca2e8e39a03c stopped answ
  job.retrying   attempt 2     +4.9 s  retry 1 of 2
  job.scheduled  attempt 2     +4.9 s  
  job.running    attempt 2    +25.2 s  
  job.succeeded  attempt 2    +42.5 s  

job-37: SUCCEEDED, attempt 2; worker started again 5.2 s after the kill
  job.queued     attempt 1     -3.2 s  
  job.scheduled  attempt 1     -3.2 s  
  job.running    attempt 1     -3.2 s  
  job.failed     attempt 1     +5.1 s  no heartbeat for 6 seconds (worker-ca2e8e39a03c stopped answ
  job.retrying   attempt 2     +5.1 s  retry 1 of 2
  job.scheduled  attempt 2     +5.1 s  
  job.running    attempt 2    +25.3 s  
  job.succeeded  attempt 2    +42.5 s  

seconds after the kill   run  1  run  2  run  3
job.failed (detected)       6.1     4.9     5.1
job.retrying                6.1     4.9     5.1
running again (try 2)      26.6    25.2    25.3
job.succeeded              43.9    42.5    42.5
```

## Summary

| Seconds after the kill | Run 1 | Run 2 | Run 3 |
|---|---|---|---|
| Job marked FAILED ("no heartbeat for 6–7 seconds") | 6.1 | 4.9 | 5.1 |
| Retried (`job.retrying`, attempt 2) and scheduled | 6.1 | 4.9 | 5.1 |
| Worker started again (by the script) | 6.3 | 5.0 | 5.2 |
| Running again (attempt 2) | 26.6 | 25.2 | 25.3 |
| Succeeded (attempt 2) | 43.9 | 42.5 | 42.5 |

**3 of 3 jobs finished on their second attempt.**

**What it means.**
- **Detection** takes about the heartbeat timeout: 4.9–6.1 s with a 6 s timeout (the last heartbeat came up to
  2 s before the kill, and the sweep runs every 2 s). The retry is asked for in the same moment.
- **The restart waits about 20 s**: attempt 2 is scheduled at once but runs about 20 s later (+25 s), although the
  worker was started again 5–6 s after the kill. 20 s is the queue's visibility timeout in these settings, so most
  likely the scheduler could not hand the job to the worker while it was still starting, and the message came back
  after the timeout: the same pattern as #158. Not proven by this test (the scheduler log was not read).
- **Training** then takes about 17 s (300 epochs on 8 rows).
- **With the normal settings** (120 s timeout, 10 s sweep, 300 s visibility) the same steps would take about
  2 minutes to detect and up to 5 more minutes to run again. Derived from the settings, not measured.

In the cloud a dead machine is replaced by its Auto Scaling group, which takes minutes, not the 5 s of
`docker compose start` here.
