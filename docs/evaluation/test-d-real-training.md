# Test D: real training jobs on the laptop (raw results)

**Measured:** Sun 22 Nov 2026, 11:20–11:43 (UTC+4), by Adel on the laptop in section 0 of `EVALUATION.md`.
**Versions:** `main` at `7b77c76`, with the real training worker (#93, Abdullah), the scheduler's machine types
(#105, #139, Maitha) and the monitoring stack (#115). All 15 containers healthy after `make up`.
**Workload:** the walk-through's job (steps 4–7): model `tabular_mlp` on the Wisconsin breast-cancer data
(decision 0008), real training on the laptop CPU, metrics in MLflow, model saved to LocalStack S3.

## 1. The walk-through, 10 times

```bash
for i in 1 2 3; do echo "=== run $i ==="; time make e2e; done
for i in 4 5 6 7 8 9 10; do echo "=== run $i ==="; make e2e | tail -1; done
```

Every run: `22 passed, 7 skipped` (the skips name their owners: login step with the dev token, failure test,
machine release, 1-GPU vs DDP, model registry and prediction). Time of a run: 24.84 s (run 1), then
5.53, 5.44, 5.52, 5.45, 5.54, 5.47, 5.56, 5.43, 5.49 s.

## 2. From Prometheus (`job-events-monitor` and the scheduler)

```bash
q() { docker compose exec -T prometheus promtool query instant http://localhost:9090 "$1"; }
# after runs 1-3
q 'increase(cloudtrain_job_events_total{event_type="job.succeeded"}[30m])'          # => 3.06
q 'increase(scheduler_jobs_placed_total[30m])'                                       # => 3.18
q 'sum(increase(cloudtrain_job_queue_wait_seconds_sum[30m])) / sum(increase(cloudtrain_job_queue_wait_seconds_count[30m]))'   # => 0.0359
q 'sum(increase(cloudtrain_job_run_seconds_sum{result="SUCCEEDED"}[30m])) / sum(increase(cloudtrain_job_run_seconds_count{result="SUCCEEDED"}[30m]))'   # => 6.53
# after runs 1-10
q 'sum(increase(cloudtrain_job_queue_wait_seconds_count[60m]))'                       # => 10.24
q 'histogram_quantile(0.50, sum by (le) (increase(cloudtrain_job_queue_wait_seconds_bucket[60m])))'   # => 0.5
q 'histogram_quantile(0.95, sum by (le) (increase(cloudtrain_job_queue_wait_seconds_bucket[60m])))'   # => 0.95
q 'histogram_quantile(0.50, sum by (le) (increase(cloudtrain_job_run_seconds_bucket{result="SUCCEEDED"}[60m])))'   # => 5.625
q 'histogram_quantile(0.95, sum by (le) (increase(cloudtrain_job_run_seconds_bucket{result="SUCCEEDED"}[60m])))'   # => 21.0
```

Counts are not whole numbers because `increase()` extrapolates to the edges of the window.

**The quantiles say little here.** The smallest bucket is 1 s for the queue wait and 10 s for the run time
(chosen for GPU jobs of minutes to hours; #153 adds smaller ones). The queue waits all fall in the first
bucket, so p50 and p95 are only guesses inside it ("under 1 s"). For the run time, 9 of the 10 jobs fall in
the first bucket (under 10 s) and one, the cold start at 12.7 s, in the next (10–30 s): that one job is why
p95 says 21 s, a guess inside the 10–30 s bucket, not a measured time.

**The averages are estimates, not exact.** Sum ÷ count divides two `increase()` values over the same window,
so the extrapolation mostly cancels out, but it is still a window average from Prometheus, not a per-job
measurement. The averages above cover **runs 1–3 only** (3 jobs). The exact per-job times are in section 3,
from the jobs' own `started_at` and `finished_at`.

## 3. Every job, from Training Jobs (through the gateway)

[`jobs.py`](jobs.py) lists each project's jobs: status, machine type, GPU-hours, estimated cost, and
`finished_at − started_at` (standard library only; reads `GET /api/v1/projects` and
`GET /api/v1/jobs?project_id=…`). The run on 22 Nov used a throwaway copy in `/tmp` that was not kept;
`jobs.py` is a re-creation that prints the same columns.

```bash
export DEV_AUTH_TOKEN=$(grep '^DEV_AUTH_TOKEN=' .env | cut -d= -f2)
python3 docs/evaluation/jobs.py
```

```
job-01 SUCCEEDED local-cpu gpu_hours: 0.0 cost: 0.0 run_s: 3.0
job-02 SUCCEEDED local-cpu gpu_hours: 0.0 cost: 0.0 run_s: 3.0
job-03 SUCCEEDED local-cpu gpu_hours: 0.0 cost: 0.0 run_s: 3.0
job-04 SUCCEEDED local-cpu gpu_hours: 0.0 cost: 0.0 run_s: 3.0
job-05 SUCCEEDED local-cpu gpu_hours: 0.0 cost: 0.0 run_s: 3.0
job-06 SUCCEEDED local-cpu gpu_hours: 0.0 cost: 0.0 run_s: 3.0
job-07 SUCCEEDED local-cpu gpu_hours: 0.0 cost: 0.0 run_s: 12.7
job-08 SUCCEEDED local-cpu gpu_hours: 0.0 cost: 0.0 run_s: 3.8
job-09 SUCCEEDED local-cpu gpu_hours: 0.0 cost: 0.0 run_s: 3.1
job-10 SUCCEEDED local-cpu gpu_hours: 0.0 cost: 0.0 run_s: 4.0
job-11 SUCCEEDED local-cpu gpu_hours: 0.0 cost: 0.0 run_s: 3.1
job-12 SUCCEEDED local-cpu gpu_hours: 0.0 cost: 0.0 run_s: 3.0
job-13 SUCCEEDED local-cpu gpu_hours: 0.0 cost: 0.0 run_s: 2.9
job-14 SUCCEEDED local-cpu gpu_hours: 0.0 cost: 0.0 run_s: 2.9
job-15 SUCCEEDED local-cpu gpu_hours: 0.0 cost: 0.0 run_s: 2.9
job-16 SUCCEEDED local-cpu gpu_hours: 0.0 cost: 0.0 run_s: 2.9
```

`job-01` to `job-06` are from 20–21 Nov and ran on the **stand-in worker** (a fixed 3 s); they are not part of
this test. **`job-07` to `job-16` are today's 10 real training jobs.**

## Summary (the 10 real jobs)

| Measure | Result |
|---|---|
| Succeeded | 10 of 10, no retry, no failure |
| Wait in the queue (QUEUED → RUNNING) | average **36 ms** over **runs 1–3 only** (3 jobs; a Prometheus window average, section 2); the histogram puts all 10 under 1 s |
| Training time (RUNNING → SUCCEEDED) | median **3.05 s**, range 2.9–12.7 s, from each job's `started_at` and `finished_at` (section 3); the first job (12.7 s) includes the worker's cold start |
| Whole walk-through | 24.8 s the first time, then 5.4–5.6 s |
| Machine chosen by the scheduler | `local-cpu` for all 10 (no GPU asked) |
| GPU-hours and estimated cost | 0.0 GPU-hours, **$0.00** for every job: the real price of `local-cpu` in `contracts/pricing.yaml`, not a missing value |
| Jobs counted by the scheduler | 3 for runs 1–3, so the first jobs are counted (#138, fixed in #139) |

Laptop CPU, small tabular model: these numbers show the platform's own overhead, not GPU training speed
(that is `docs/BENCHMARKS.md`, Ahmed + Abdulla).
