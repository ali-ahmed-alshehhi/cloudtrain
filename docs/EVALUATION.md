# Evaluation: performance, reliability and cloud cost

**Owners:** Hilal + Adel (Student 10). **Status on 25 Nov 2026: Tests A to J measured on a laptop, including single vs DDP
through the platform (J, 2 processes on CPU). Not measured: DDP on real GPUs (no AWS account, decision 0011).** Final version: Fri 27 Nov.

## Headline results

All measured on one laptop with Docker Compose (section 0), so they show how the platform behaves, not cloud
speed. Each links to its row below and to the raw output.

| | Result |
|---|---|
| Gateway speed | p50 **2.9–7.7 ms**, p95 **19–50 ms** per route (Test C) |
| A service stops or freezes | the gateway answers **503 at once** (stopped) or **after 10 s** (frozen), never hangs, and works again on the first request after the restart; tested on 5 services (Test A). Alert "service down" fires after **83–88 s** |
| Restart (`make down` + `make up`) | **records kept** (projects, jobs, datasets, MLflow experiments and runs); **local S3 files lost**, as decision 0005 expects (Test B) |
| Dataset transfer | upload **154–161 MB/s**, download **253–270 MB/s** (medians of 3, 52 MB and 524 MB files; Test C) |
| A burst of jobs | 3 jobs sent at once with one worker: waits **0.1 s, 300 s and 729 s** for about 4 s of training each. A job that finds the worker busy comes back only after the queue's 300 s visibility timeout; the cloud uses the same settings (Test F) |
| The whole website | with every page on `main`: **6 of 6 browser tests** pass on the real stack, including a training job submitted in the browser and followed to its MLflow results; `make e2e` 25 passed (Test I) |
| Worker killed mid-job | detected in **about 5 s** (6 s timeout), retried at once, running again after **about 25 s** and finished, 3 of 3 runs (short test settings; Test H) |
| Prediction | **p50 3.2 ms, p95 4.4 ms** through the gateway, 100 of 100 answered, with the walk-through's small test model: the platform's serving path, not a trained model (Test G) |
| Alert delay in the portal | an alert is on the Projects page **2.3 s** (median) after the job event, never more than **5.0 s** (the page's 5 s poll); 40 of 40 alerts shown (Test E) |
| 10 real training jobs | **10 of 10 succeeded**; time per job median **3.05 s** on the laptop CPU, with the walk-through's tiny 8-row CSV (platform overhead, not training on real data); queue wait average 36 ms (runs 1–3) (Test D) |
| Cost | **$0 spent** (no AWS account, decision 0011). Local jobs run on `local-cpu`, priced $0. GPU costs in this report are estimates of what AWS would charge |
| Single vs DDP | through the whole platform, **2 processes on CPU, local stack**: each epoch **1.50× faster** (26.6 → 17.8 ms, 75% efficiency), but each DDP job **0.7 s longer** end to end; the comparison page shows the same numbers (Test J). On Abdulla's laptop: 0.96×. Not on GPUs |
| Not measured | DDP on real GPUs, and anything on AWS (no account, decision 0011) |

**How to read the status column**

| Mark | Meaning |
|---|---|
| ✅ Measured | A real number from the integrated system or a real GPU run, with the file or log it comes from |
| 🧪 Tested | The behaviour is checked by an automated test (often with a fake clock or FIXTURE data). It shows the logic is right, **not** how long it takes in the running system |
| ⏳ Not measured yet | Method fixed, number pending. "Waiting on" names who and by when |

No number in this report is invented, estimated by hand or taken from FIXTURE data. Simulated or emulated
results are always labelled as such ([decision 0011](decisions/0011-aws-emulator-instead-of-aws-account.md): AWS Emulator, no AWS account).

## What the evaluation found

Measuring the running system also found problems. Each was reported to its owner with the commands and the
raw output, and most are fixed:

| Found by | Problem | Issue | Fix |
|---|---|---|---|
| Checking the Grafana dashboard (#115), 20 Nov | The scheduler's metrics were created only when the first job arrived, so the first jobs were missing from "jobs placed" | #138 | #139 (Maitha), merged 21 Nov |
| Test B (restart), 21 Nov | A dataset file missing from S3 was reported as "Object storage is not reachable" (503), not as missing (404) | #126 | #142 (Faisal), merged 22 Nov |
| Test F (burst), 22 Nov | A job that arrives while the only worker is busy waits for the 300 s queue timeout: 3 short jobs took 12 min | #158 | #161 (Maitha), in review: re-tested on the laptop, 3 jobs in 13.2 s |
| Re-testing the first version of #161, 23 Nov | A retried job stays `SCHEDULED` forever when every hand-off to a worker fails (`dropped_already_handled` = 1) | #167 | #168 (Mariam), merged 23 Nov |

## 0. Setup

| | Value |
|---|---|
| Where everything runs | Docker Compose on a laptop (`make up`): 12 containers, i.e. the 9 CloudTrain services plus Postgres, LocalStack (S3, SQS) and MLflow; 15 with the monitoring stack (#115, on `main` since 22 Nov) |
| Laptop used for Tests A to J | MacBook Pro, Apple M5 Pro (arm64), 48 GB RAM, macOS 27.2.1; Docker Engine 29.9.2 and Docker Compose v5.6.1, with 7.7 GiB of memory for the containers |
| "Cloud" | The AWS Emulator with the same Terraform ([decision 0011](decisions/0011-aws-emulator-instead-of-aws-account.md), merged in #112): checks the infrastructure, runs no real machines |
| GPUs | Real GPU runs only on a team workstation (Ahmed + Abdulla, `docs/BENCHMARKS.md`). No cloud GPU |
| Monitoring | Prometheus + Grafana dashboard "CloudTrain overview" and `job-events-monitor` (`monitoring/`, #115, #109) |
| Versions | Recorded with each measurement (Git commit, `docker compose version`, Python, Node 24, PyTorch for GPU runs) |
| Repeats | Timings are repeated at least 3 times, with the median and the spread, except where a row says otherwise (Test A on datasets, jobs, models and MLflow: one request per case) |

## 1. Performance

| What | Method | Status | Result | Evidence |
|---|---|---|---|---|
| Gateway latency per route, p50 / p95 | Prometheus histogram `gateway_request_duration_seconds` while `make e2e` runs 3 times; dashboard panel "Slowest 5% of answers" | ✅ Measured on a laptop (20 Nov, #115 at `aa6cc8b`) | p50: projects 2.9 ms, datasets 7.0 ms, jobs 7.7 ms, experiments 7.5 ms. p95: 19, 19, 22 and 50 ms. About 75 requests; values are estimates inside the histogram buckets (5, 10, 25, 50 ms) | [`docs/evaluation/test-c-speed-and-alert.md`](evaluation/test-c-speed-and-alert.md) |
| Time from `POST /jobs` to RUNNING (queue + scheduling) | `cloudtrain_job_queue_wait_seconds` from `job-events-monitor` (QUEUED → RUNNING per attempt), 10 small jobs | ✅ Measured on a laptop (22 Nov, `main` at `7b77c76`, real training worker) | **Average 36 ms over runs 1–3 (3 jobs)**, a Prometheus window average (sum ÷ count of `increase()`), not a per-job measurement. The histogram puts all 10 jobs under 1 s; its smallest bucket is 1 s, so its p50/p95 say only "under 1 s" (#153 adds smaller buckets) | [`docs/evaluation/test-d-real-training.md`](evaluation/test-d-real-training.md) |
| Training time per job | `cloudtrain_job_run_seconds{result}` and the job's `started_at` → `finished_at`, same 10 jobs | ✅ Measured on a laptop (22 Nov, `7b77c76`): `tabular_mlp`, 1 epoch on the walk-through's tiny 8-row Wisconsin-style CSV, laptop CPU. This is the platform's overhead, not training on real data | **Median 3.05 s**, 2.9–12.7 s (the first includes the worker's cold start); 10 of 10 succeeded. Whole walk-through: 24.8 s the first time, then 5.4–5.6 s | [`docs/evaluation/test-d-real-training.md`](evaluation/test-d-real-training.md) |
| Alert delay: status change → visible in the portal | `occurred_at` of the event vs the time the alert appears in the browser (Playwright), plus `cloudtrain_job_event_lag_seconds` for the monitor | ✅ Measured on a laptop (22 Nov, `db26b20`): 10 real jobs, alerts on the Projects page (#99) in headless Chrome. The job page itself (#165, merged 24 Nov) shows the same alerts, from the same feed; its delay was not measured separately | **Median 2.30 s**, 0.58–4.98 s from the event to its alert; **40 of 40** events shown. Submit → "is queued" alert: median 2.21 s, max 5.00 s (one clock). The monitor reads an event in about 6 ms (window average), so the delay is the page's 5 s poll (contract: 5–10 s) | [`docs/evaluation/test-e-alert-delay.md`](evaluation/test-e-alert-delay.md) |
| Inference latency `POST /predict` | 100 requests through the gateway after one warm-up; p50 / p95 | ✅ Measured on a laptop (22 Nov, `1bb2326`), with the walk-through's small image **test model** (step 10), not a trained model: the serving path only | **p50 3.2 ms, p95 4.4 ms** (min 2.6, max 6.1); 100 of 100 answered 200; first request 9.5 ms. One client, one request at a time (not a load test) | [`docs/evaluation/test-g-predict-latency.md`](evaluation/test-g-predict-latency.md) |
| Dataset upload / download speed | Upload and download a 50 MB and a 500 MB file through the gateway, 3 times each, MB/s | ✅ Measured on a laptop (20 Nov, `aa6cc8b`), with `curl` through the gateway (the portal page, #99, is not needed for this) | **52 MB:** upload 161 MB/s, download 253 MB/s. **524 MB:** upload 154 MB/s, download 270 MB/s (medians of 3). Every download returned the exact size; speed per MB stays the same for the bigger file. One laptop, no network: upper bounds | [`docs/evaluation/test-c-speed-and-alert.md`](evaluation/test-c-speed-and-alert.md) |

## 2. Reliability

| Scenario | Expected behaviour | Status | Result | Evidence |
|---|---|---|---|---|
| Worker killed mid-job | Heartbeat stops → FAILED after the timeout (120 s, 6 s in the demo settings) → retried → SUCCEEDED; time to detect and time to recover | 🧪 Tested in job-service (fake clock), and **end to end in CI** since #145 (Mariam, merged 22 Nov): the real worker is killed mid-job, the job is marked FAILED for its stopped heartbeat, retried, and finishes on attempt 2 (short heartbeat settings). ✅ **Times measured on a laptop** (22 Nov, `1bb2326`, short settings: 6 s timeout, 20 s visibility), 3 runs | Marked FAILED **4.9–6.1 s** after the kill and retried at once; running again after **25–27 s** (about 20 s waiting, most likely the 20 s visibility timeout, as in #158); finished after 42.5–43.9 s; **3 of 3** on attempt 2. With the normal settings: about 2 min to detect and up to 5 min more (derived, not measured) | [`docs/evaluation/test-h-recovery.md`](evaluation/test-h-recovery.md); `job-service/tests/test_recovery.py`, `tests/integration/test_failure_recovery.py` (runs in CI; on a laptop only with the short settings) |
| Retries used up | FAILED for good and reported to the dead-letter queue; dashboard alert `CloudTrainDeadLetters` | 🧪 Tested (job-service, alert rule) | | `test_retries_used_up_stays_failed_and_reports_to_the_dlq`, `monitoring/prometheus/alerts.test.yml` |
| A service stopped or too slow | The gateway answers 503 in the shared error format, nothing hangs; alert `CloudTrainServiceDown` after 1 min | ✅ Measured in Compose: Projects (19 Nov, `f8d8dab`), then datasets, jobs, models and MLflow (21 Nov, `b404125`). ✅ Alert in Compose (20 Nov, #115 at `aa6cc8b`): pending after 26–31 s, **firing after 83–88 s** (rule: 1 min, checks every 15 s), cleared 26–31 s after the restart | **Stopped:** 503 × 5, median 4.1 ms, `SERVICE_UNAVAILABLE` + `request_id`; gateway `/health` stays 200. **Frozen:** 503 × 3 after 10.01 s (the 10 s timeout). **Back:** 200 on the first request, 4.7 ms median, no restart. Normal: 7.2 ms median. **The same for datasets, jobs, models and MLflow:** stopped 503 in 6–29 ms, frozen 503 after 10.004–10.007 s, back 200 at once | [`docs/evaluation/test-a-service-stopped-or-frozen.md`](evaluation/test-a-service-stopped-or-frozen.md), [`docs/evaluation/test-c-speed-and-alert.md`](evaluation/test-c-speed-and-alert.md) (alert), `gateway/tests/test_gateway.py::test_503_when_a_service_is_down_or_slow` |
| Duplicate or out-of-order job events | Counted once; durations right in any order (at-least-once SQS, confirmed by Mariam on #109) | 🧪 Tested, including a recording of what job-service sends | | `monitoring/job-events-monitor/tests/` |
| Portal when the gateway or a service is down | Clear message, retries with back-off (alerts 10 s → 60 s), never another project's or job's data | 🧪 Tested (portal unit tests, Chrome checks with FIXTURE pages) | | `portal/test/`, #96, #98, #100, #117 |
| Restarting containers keeps data | Datasets, models, experiments and job records still there after `make down && make up` | ✅ Measured locally: projects and datasets (19 Nov, `f8d8dab`); all 20 projects, 6 jobs with their status, 25 dataset records and the MLflow experiment list (21 Nov, `b404125`). ✅ MLflow experiments and **all 21 MLflow runs** with their metrics and tags, 53 projects and 27 jobs (22 Nov, `db26b20`, part 3). Not measured: registered models (none yet: registering is Majed's skipped step) and model files (the check could not see MLflow 3's logged models) | **Records (PostgreSQL): kept**: identical lists before and after (projects, jobs and their status, datasets, MLflow experiments). **Files (LocalStack S3): lost**, the download answers 503, as [decision 0005](decisions/0005-localstack-for-s3.md) says (free LocalStack keeps S3 in memory; real S3 in the cloud is not affected). On 19 Nov the answer was a misleading 503 "Object storage is not reachable" (#126); since #142 (Faisal, 22 Nov) it is 404 `DATASET_FILE_MISSING` | [`docs/evaluation/test-b-restart-keeps-data.md`](evaluation/test-b-restart-keeps-data.md) |

## 3. Scalability

| What | Status | Result | Evidence |
|---|---|---|---|
| What scales separately and how | ✅ Read from the code (22 Nov, `main` at `a21d01c`); not measured on AWS (no account) | **Training:** GPU workers in two EC2 Auto Scaling groups (decision 0012): `gpu-1` (`g4dn.xlarge`, `worker_desired_capacity`, at most `worker_max_size` = 2) and `gpu-4` (`g4dn.12xlarge`, at most 1). The size changes with one `terraform apply`; nothing scales it automatically. **Services:** each is its own ECS Fargate service, but Terraform gives all of them the same `ecs_desired_count` (1 in the dev settings) and no autoscaling; the gateway and portal sit behind the load balancer. **Between them:** SQS. `POST /jobs` answers 202 at once and the job waits in `training-jobs`, so a burst of submissions never blocks the API. **Limit:** the scheduler places only `SCHEDULER_MAX_WORKERS` jobs at once (default 1, not set in Terraform), so more GPU machines alone do not run more jobs at once (Test F) | `infrastructure/main.tf`, `infrastructure/README.md`, decision 0012, `scheduler/app/main.py` |
| A burst of jobs with one worker | ✅ Measured on a laptop (22 Nov, `db26b20`): 3 small CPU jobs submitted at the same moment | Waits **0.1 s, 300.3 s and 729.2 s**; together they needed about 11 s of training and took **732 s**. A job that arrives while the worker is busy is turned away and SQS hides it for the 300 s visibility timeout (3 "no capacity" lines in the scheduler log). The 729 s includes a pause of the laptop of about 3.5 min; the code predicts about 600 s. Fixes are the Scheduler owner's call (Maitha): reported as #158 | [`docs/evaluation/test-f-burst.md`](evaluation/test-f-burst.md) |
| 1 vs 2-process DDP: speedup, efficiency, throughput, GPU-hours | ✅ Measured on a laptop (25 Nov, `b087330`): Abdulla's `platform_compare` (#173), 3 seeds each, read back with `compare_runs.py` and on `/compare`. **Where it ran: 2 processes on CPU, local stack**, not GPUs. ⏳ Not measured: DDP on real GPUs (no AWS account) | Time per epoch 26.6 → 17.8 ms: **speedup 1.50×, efficiency 75%**; throughput 16,822 → 25,194 rows/s; job wall time 4.9 → 5.6 s; accuracy 0.968 both. On Abdulla's laptop 0.96× (`docs/BENCHMARKS.md`): with 15–30 ms epochs the result depends on the machine | [`docs/evaluation/test-j-single-vs-ddp.md`](evaluation/test-j-single-vs-ddp.md), `docs/BENCHMARKS.md` section 2, #76 |
| Local 1-GPU baseline (not the comparison) | ✅ Measured by Ahmed + Abdulla on 1× RTX 5090 | CIFAR-10, ResNet-18, 10 epochs: 2.0 s per epoch, 74.0% accuracy (3 seeds) | `docs/BENCHMARKS.md`, `docs/benchmarks/local-cifar10-1gpu-baseline.json` |

## 4. Cloud cost

**Method.** Training Jobs computes `gpu_hours` and `estimated_cost_usd` for every job: on-demand hourly
price of the machine type × machine time, summed over every attempt (failed attempts count too). The
portal only adds up a project's jobs (#117). An unknown price is `null` and shown as "Price unknown",
never $0 (#108, #114). Prices: `contracts/pricing.yaml`, real us-east-1 on-demand prices copied from AWS on 17 Nov 2026 (#111).
All three are on `main` since 18 Nov.

| Machine type (`contracts/pricing.yaml`) | GPUs | USD per hour |
|---|---|---|
| `local-cpu` (laptop worker) | 0 | 0 (free) |
| `c6i.2xlarge` | 0 | 0.34 |
| `g4dn.xlarge` | 1 × T4 | 0.526 |
| `g4dn.12xlarge` | 4 × T4 | 3.912 |
| `g4dn.metal` | 8 × T4 | 7.824 |

| What | Status | Result | Evidence |
|---|---|---|---|
| Cost per job and per project | ✅ Real jobs (22 Nov): the scheduler chose `local-cpu` for all 10, so 0.0 GPU-hours and **$0.00** each, the real price of `local-cpu` (not a missing value). Portal views on `main` (#117), tested with FIXTURE jobs for GPU prices; shown on the pages `/usage` and `/compare` (#156, merged 22 Nov). A GPU job's cost needs a GPU machine, which the laptop and the AWS Emulator do not have | | `portal/components/usage/`, `portal/test/usage.test.mjs` |
| Cost of the single vs DDP runs | ✅ From Training Jobs for the Test J runs | GPU-hours as billed 0.0014 (single) and 0.0031 (DDP) per job; cost **$0.00**, because `local-cpu` is priced $0. On GPUs it would be GPU-hours × the price in `contracts/pricing.yaml`: not measured | [`docs/evaluation/test-j-single-vs-ddp.md`](evaluation/test-j-single-vs-ddp.md) |
| Total cloud spend | **$0: no AWS account.** The team uses the AWS Emulator (decision 0011), so all costs in this report are **estimates of what the same work would cost on AWS**, not bills | | [decision 0011](decisions/0011-aws-emulator-instead-of-aws-account.md) |
| Keeping cost down | ✅ Checked in the code (20 Nov, `main` at `474a732`). **1. Smallest machine that fits:** the scheduler picks 0 GPU → `c6i.2xlarge`, 1 → `g4dn.xlarge`, 2–4 → `g4dn.12xlarge`, 5–8 → `g4dn.metal` (`scheduler/app/machines.py`, #105); locally always `local-cpu` ($0). **2. Machines are not started and stopped per job:** each GPU pool has a fixed size set in Terraform (`worker_desired_capacity`, 1 in the dev settings; the 4-GPU pool 0; min 0), with no autoscaling, so a machine costs money while idle: one idle `g4dn.xlarge` ≈ **$12.62 a day** (24 h × $0.526). Saving money is manual: set the capacity to 0 when nobody trains, `terraform destroy` after use. **3.** The scheduler frees a job's slot only when the next job needs one ("Busy workers" stays 1 after a job); that affects placement, not the bill | | `scheduler/app/machines.py`, `infrastructure/main.tf`, `infrastructure/README.md` ("Demo 4"), `contracts/pricing.yaml` |

## 5. Observability (monitoring)

| What | Status | Evidence |
|---|---|---|
| Every service serves `/health` and `/metrics` | ✅ On `main` (shared service helper) | `*/app/common.py` |
| `job-events` read by exactly one reader, metrics per attempt | 🧪 Tested (25 tests). ✅ Runs in Compose (#115, merged 22 Nov): Healthy in CI (`make up`, and the Real login job) and on a laptop, 20 Nov | #115 |
| Dashboard "CloudTrain overview", 5 alert rules | ✅ Seen working on a laptop (20 Nov, #115 at `3fbdf42`): all 10 services UP, 0 alerts firing, time since the last `job-events` read 0–20 s (the 20 s long poll; alert at 120 s). Job and queue panels said "No data yet" until real training jobs ran (#93); on 22 Nov they counted the 10 jobs of Test D. This first run found two display bugs (a "56 years" spike before the first read, a 10000% axis), fixed in `3fbdf42`. 🧪 Alert rules unit-tested with promtool | `monitoring/README.md` |
| AWS side: CloudWatch alarms, dashboard and the monitor | ✅ On `main` (22 Nov): **3 alarms and a log group per service in Terraform** (#134, Fatma + Hamda; the server-errors alarm only once the load balancer of #135 exists). They match 3 local rules on AWS's own metrics, with different conditions (table in decision 0014, #152). ✅ **The CloudWatch dashboard** is a separate Pulumi layer (decision 0013, #149, Fatma). ⏳ **`job-events-monitor` is not deployed on AWS** (#135 does not start it), so no `cloudtrain_job_*` metrics reach CloudWatch; waiting on: Adel to agree an owner with Hamda + Fatma (Mon 23 Nov). On the emulator: setup only, no live data | #134, #149, `infrastructure/modules/monitoring/`, `monitoring/aws/` |

## 6. Limitations

- **No real cloud.** The AWS Emulator checks the infrastructure but runs no machines (decision 0011), so
  there is no measured cloud latency, cloud GPU performance or real bill.
- **GPU numbers come from one workstation**, not from the machine types priced in `contracts/pricing.yaml`.
- **Laptop timings** include Docker on a laptop and are not production numbers.
- **Test A covers 5 services** (projects, datasets, jobs, models, MLflow). Not tested: `predict` and the
  upload routes, which wait up to 300 s (`GATEWAY_UPLOAD_TIMEOUT_SECONDS`) before 503.
- **Locally, uploaded files do not survive a restart** (Test B, decision 0005): after `make down` +
  `make up`, datasets must be uploaded again before training on them.
- **LocalStack serves both S3 and SQS on the laptop.** During the 500 MB uploads (Test C) the time since the
  last `job-events` read rose to about 55 s on the dashboard (normally 0–20 s), still under the 120 s alert.
  In the cloud, S3 and SQS are separate services.
- **One job at a time.** With the current settings (local and cloud), the scheduler runs one job at once, and a
  job that arrives while another runs waits about 300 s per turn (Test F). Until that changes, bursts of jobs
  are slow and extra GPU machines stay idle.
- `job-events-monitor` keeps durations and counters in memory: a restart forgets jobs in flight, and its
  counters start again from 0. Prometheus treats that as a counter reset, so `rate()` and `increase()` stay
  right; events are not lost (unread ones wait in SQS).
- Tensor and pipeline parallelism are not evaluated (`docs/BENCHMARKS.md`: never simulated).

## 7. How to reproduce

Everything goes through the gateway (port 5810) with the local dev login, read from `.env`:

```bash
make up                                   # 15 containers
TOKEN=$(grep '^DEV_AUTH_TOKEN=' .env | cut -d= -f2); H="Authorization: Bearer $TOKEN"
open http://localhost:3001                # Grafana, dashboard "CloudTrain overview"
```

| Test | What it shows | Commands and raw output |
|---|---|---|
| A | A service stopped or frozen: the gateway answers 503 at once or after 10 s, and recovers; the alert fires | [`evaluation/test-a-service-stopped-or-frozen.md`](evaluation/test-a-service-stopped-or-frozen.md), [`evaluation/test-c-speed-and-alert.md`](evaluation/test-c-speed-and-alert.md) (part 3) |
| B | What survives `make down` + `make up` (records yes, including MLflow runs; local S3 files no) | [`evaluation/test-b-restart-keeps-data.md`](evaluation/test-b-restart-keeps-data.md) |
| C | Gateway p50/p95, dataset upload and download speed | [`evaluation/test-c-speed-and-alert.md`](evaluation/test-c-speed-and-alert.md) |
| D | 10 real training jobs: queue wait, training time, machine and cost per job | [`evaluation/test-d-real-training.md`](evaluation/test-d-real-training.md) |
| E | Alert delay: job event → alert on the Projects page, 10 jobs | [`evaluation/test-e-alert-delay.md`](evaluation/test-e-alert-delay.md) |
| F | A burst of 3 jobs with one worker: wait in the queue per job | [`evaluation/test-f-burst.md`](evaluation/test-f-burst.md) |
| G | Prediction latency through the gateway, 100 requests | [`evaluation/test-g-predict-latency.md`](evaluation/test-g-predict-latency.md) |
| H | Worker killed mid-job: time to detect, retry and finish, 3 runs | [`evaluation/test-h-recovery.md`](evaluation/test-h-recovery.md) |
| I | The whole website, end to end: all six browser tests and the walk-through on the real stack | [`evaluation/test-i-website-e2e.md`](evaluation/test-i-website-e2e.md) |
| J | Single vs DDP through the platform (2 processes on CPU), read on the comparison page | [`evaluation/test-j-single-vs-ddp.md`](evaluation/test-j-single-vs-ddp.md) |

The automatic checks behind the "🧪 Tested" lines:

```bash
make e2e                                                    # the walk-through, through the gateway
cd monitoring/job-events-monitor && python -m pytest        # 25 tests (#115)
cd monitoring/prometheus && promtool test rules alerts.test.yml
cd portal && npm test                                       # portal unit tests
```

## 8. Contributions

| Who | Part of this evaluation |
|---|---|
| Adel | This report and its methods; Tests A to J on a laptop; the job-events reader, Prometheus alerts and Grafana dashboard (#115, contract #125, decision 0014 in #152); live job status and alerts (#96, #100), MLflow results (#98), cost views (#117), the 1-GPU vs multi-GPU comparison (#124) and their pages `/compare` and `/usage` (#156) in the portal. Problems found and reported while measuring: #126 (Faisal), #138 (Maitha, fixed in #139) |
| Hilal | Portal pages (#99: projects, datasets, job alerts on the Projects page; #165: submit a training job, the jobs list and the live job page) and their browser tests (functional checks, passing). ⏳ Browser timings: recorded here once measured |
| Ahmed + Abdulla | GPU benchmarks (`docs/BENCHMARKS.md`) |
| Mariam | Job timings, retries and cost fields (Training Jobs) |
| Fatma + Hamda | The CloudWatch log groups and alarms in Terraform (#134); the CloudWatch dashboard as a Pulumi layer (#149, Fatma) |
| Everyone | `/metrics` in every service; the integrated runs |
