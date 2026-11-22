# Test F: a burst of jobs at once (raw results)

**Measured:** Sun 22 Nov 2026, 12:55–13:07 (UTC+4), by Adel on the laptop in section 0 of `EVALUATION.md`.
**Versions:** branch `adel/compare-cost-pages` at `db26b20` (`main` at `0cf0f1c` + #156; the scheduler is
`main`'s). Local settings from `.env.example`: one training worker, `SCHEDULER_MAX_WORKERS` not set (default 1),
`SQS_VISIBILITY_TIMEOUT_SECONDS=300`.
**Question:** what happens when several jobs arrive while the only worker is busy?

## What the code says (`scheduler/app/main.py`, `main` at `a21d01c`)

The scheduler reads `training-jobs` one message at a time. When no slot is free (`SCHEDULER_MAX_WORKERS`,
default 1) and the running job has not ended yet, it logs `no capacity; message stays on queue` and leaves the
message without deleting it or changing its visibility. SQS then hides that message for the queue's visibility
timeout (300 s, `local/localstack/init.sh`; the same variable in Terraform). So a job that arrives while another
runs is expected to wait about 300 s, even if the other job ends after a few seconds, and 300 s more each time it
is turned away again.

## Commands

```bash
make e2e                                   # a fresh dataset in LocalStack S3 (Test B: files go on restart)
export DEV_AUTH_TOKEN=$(grep '^DEV_AUTH_TOKEN=' .env | cut -d= -f2)
python3 docs/evaluation/burst.py 3         # 3 jobs submitted at the same moment
docker compose logs scheduler | grep -c "no capacity"
```

[`burst.py`](burst.py) submits the walk-through's small CPU job 3 times in parallel and prints each job's wait
(`started_at − created_at`) and run time from Training Jobs (one clock).

## Output

```
Project project-56, dataset dataset-61 v1, 3 jobs
submitted 3 jobs in 0.08 s: job-30, job-29, job-31
  +     0 s: 0 of 3 ended
  +    15 s: 1 of 3 ended
  +    30 s: 1 of 3 ended
  …  (1 of 3 ended at every line up to +301 s)
  +   316 s: 2 of 3 ended
  …  (2 of 3 ended at every line up to +496 s)
  +   496 s: 2 of 3 ended
  +   705 s: 2 of 3 ended
  +   720 s: 2 of 3 ended
  +   735 s: 3 of 3 ended

job      status     created (UTC)  started   finished  wait s  run s  attempt
job-30   SUCCEEDED  08:55:09       09:00:10  09:00:14   300.3    4.0  1
job-29   SUCCEEDED  08:55:09       08:55:09  08:55:13     0.1    4.0  1
job-31   SUCCEEDED  08:55:09       09:07:18  09:07:21   729.2    3.0  1

all 3 done 732.2 s after the first was created
wait in the queue: min 0.1 s, max 729.2 s
```

```
$ docker compose logs scheduler | grep -c "no capacity"
3
```

(The progress lines between +15 s and +496 s are shortened here; each said the same as the line before.)

## Summary

| Job | Wait in the queue | Run | Turned away ("no capacity") |
|---|---|---|---|
| `job-29` | **0.1 s** | 4.0 s | 0 |
| `job-30` | **300.3 s** | 4.0 s | 1 (back after exactly the 300 s visibility timeout) |
| `job-31` | **729.2 s** | 3.0 s | 2 (expected about 600 s; see below) |

**3 jobs that need about 11 s of training together took 732 s (12 min).** The worker was idle for almost all
of that time. The 3 "no capacity" lines match: `job-30` turned away once, `job-31` twice (at the start, and again
at +300 s, most likely when it came back together with `job-30`, which took the slot).

**One gap.** The progress lines jump from +496 s to +705 s (about 3.5 min with no line, where every 15 s was
expected): the laptop very likely paused (sleep). `job-31`'s 729 s therefore includes that pause; the code
predicts about 600 s (two timeouts). `job-29` and `job-30` ended before the gap.

**What it means.** With one slot, the waiting time comes from the queue's visibility timeout, not from the work:
a burst of N short jobs takes about (N − 1) × 300 s. The same settings are used in the cloud (Terraform sets the
same 300 s timeout, and nothing sets `SCHEDULER_MAX_WORKERS`, so it is 1 there too), so more GPU machines
(`worker_desired_capacity`) would not run more jobs at once. Reported as #158. Possible fixes are the Scheduler owner's call
(Maitha), for example: give a turned-away message back sooner (`ChangeMessageVisibility` to a few seconds), wait
for the running job to end, and set `SCHEDULER_MAX_WORKERS` (and `SCHEDULER_MAX_GPUS`) from the pool sizes in
Terraform. Not measured with more than one worker: locally the scheduler has a single worker address.
