# Evaluation: performance, reliability and cloud cost

**Owners:** Hilal + Adel (Student 10). **Status on 19 Nov 2026: skeleton, measurements in: Tests A, B and C (speed, upload/download, alert), dashboard on a laptop.** The methods are fixed; most
numbers wait for the integrated system (see "Waiting on" in each table). Final version: Fri 27 Nov.

**How to read the status column**

| Mark | Meaning |
|---|---|
| ✅ Measured | A real number from the integrated system or a real GPU run, with the file or log it comes from |
| 🧪 Tested | The behaviour is checked by an automated test (often with a fake clock or FIXTURE data). It shows the logic is right, **not** how long it takes in the running system |
| ⏳ Not measured yet | Method fixed, number pending. "Waiting on" names who or what |

No number in this report is invented, estimated by hand or taken from FIXTURE data. Simulated or emulated
results are always labelled as such ([decision 0011](decisions/0011-aws-emulator-instead-of-aws-account.md): AWS Emulator, no AWS account).

## 0. Setup

| | Value |
|---|---|
| Where everything runs | Docker Compose on a laptop (`make up`): 12 containers, i.e. the 9 CloudTrain services plus Postgres, LocalStack (S3, SQS) and MLflow; 15 with the monitoring stack (#115, on `main` since 22 Nov) |
| Laptop used for Tests A, B and C | MacBook Pro, Apple M5 Pro (arm64), 48 GB RAM, macOS 27.2.1; Docker Engine 29.9.2 and Docker Compose v5.6.1, with 7.7 GiB of memory for the containers |
| "Cloud" | The AWS Emulator with the same Terraform ([decision 0011](decisions/0011-aws-emulator-instead-of-aws-account.md), merged in #112): checks the infrastructure, runs no real machines |
| GPUs | Real GPU runs only on a team workstation (Ahmed + Abdulla, `docs/BENCHMARKS.md`). No cloud GPU |
| Monitoring | Prometheus + Grafana dashboard "CloudTrain overview" and `job-events-monitor` (`monitoring/`, #115, #109) |
| Versions | Recorded with each measurement (Git commit, `docker compose version`, Python, Node 24, PyTorch for GPU runs) |
| Repeats | Timings are repeated at least 3 times, with the median and the spread, except where a row says otherwise (Test A on datasets, jobs, models and MLflow: one request per case) |

## 1. Performance

| What | Method | Status | Result | Evidence |
|---|---|---|---|---|
| Gateway latency per route, p50 / p95 | Prometheus histogram `gateway_request_duration_seconds` while `make e2e` runs 3 times; dashboard panel "Slowest 5% of answers" | ✅ Measured on a laptop (20 Nov, #115 at `aa6cc8b`) | p50: projects 2.9 ms, datasets 7.0 ms, jobs 7.7 ms, experiments 7.5 ms. p95: 19, 19, 22 and 50 ms. About 75 requests; values are estimates inside the histogram buckets (5, 10, 25, 50 ms) | [`docs/evaluation/test-c-speed-and-alert.md`](evaluation/test-c-speed-and-alert.md) |
| Time from `POST /jobs` to RUNNING (queue + scheduling) | `cloudtrain_job_queue_wait_seconds` from `job-events-monitor` (QUEUED → RUNNING per attempt), 10 small jobs | ⏳ Waiting on: #115, a real worker (#93) | | |
| Training time per job | `cloudtrain_job_run_seconds{result}` and MLflow run duration, same 10 jobs | ⏳ Waiting on: #93 | | |
| Alert delay: status change → visible in the portal | `occurred_at` of the event vs the time the alert appears in the browser (Playwright), plus `cloudtrain_job_event_lag_seconds` for the monitor | ⏳ Waiting on: #99 + job page (#59) | | |
| Inference latency `POST /predict` | 100 requests through the gateway after one warm-up; p50 / p95 | ⏳ Waiting on: Majed (prediction API, due Tue 24) | | |
| Dataset upload / download speed | Upload and download a 50 MB and a 500 MB file through the gateway, 3 times each, MB/s | ✅ Measured on a laptop (20 Nov, `aa6cc8b`), with `curl` through the gateway (the portal page, #99, is not needed for this) | **52 MB:** upload 161 MB/s, download 253 MB/s. **524 MB:** upload 154 MB/s, download 270 MB/s (medians of 3). Every download returned the exact size; speed per MB stays the same for the bigger file. One laptop, no network: upper bounds | [`docs/evaluation/test-c-speed-and-alert.md`](evaluation/test-c-speed-and-alert.md) |

## 2. Reliability

| Scenario | Expected behaviour | Status | Result | Evidence |
|---|---|---|---|---|
| Worker killed mid-job | Heartbeat stops → FAILED after the timeout (120 s, 6 s in the demo settings) → retried → SUCCEEDED; time to detect and time to recover | 🧪 Tested in job-service (fake clock). ⏳ Integrated run waiting on: Mariam + Maitha (Sat 21 – Tue 24) | | `job-service/tests/test_recovery.py`, `tests/integration/test_failure_recovery.py` (skipped until then) |
| Retries used up | FAILED for good and reported to the dead-letter queue; dashboard alert `CloudTrainDeadLetters` | 🧪 Tested (job-service, alert rule) | | `test_retries_used_up_stays_failed_and_reports_to_the_dlq`, `monitoring/prometheus/alerts.test.yml` |
| A service stopped or too slow | The gateway answers 503 in the shared error format, nothing hangs; alert `CloudTrainServiceDown` after 1 min | ✅ Measured in Compose: Projects (19 Nov, `f8d8dab`), then datasets, jobs, models and MLflow (21 Nov, `b404125`). ✅ Alert in Compose (20 Nov, #115 at `aa6cc8b`): pending after 26–31 s, **firing after 83–88 s** (rule: 1 min, checks every 15 s), cleared 26–31 s after the restart | **Stopped:** 503 × 5, median 4.1 ms, `SERVICE_UNAVAILABLE` + `request_id`; gateway `/health` stays 200. **Frozen:** 503 × 3 after 10.01 s (the 10 s timeout). **Back:** 200 on the first request, 4.7 ms median, no restart. Normal: 7.2 ms median. **The same for datasets, jobs, models and MLflow:** stopped 503 in 6–29 ms, frozen 503 after 10.004–10.007 s, back 200 at once | [`docs/evaluation/test-a-service-stopped-or-frozen.md`](evaluation/test-a-service-stopped-or-frozen.md), [`docs/evaluation/test-c-speed-and-alert.md`](evaluation/test-c-speed-and-alert.md) (alert), `gateway/tests/test_gateway.py::test_503_when_a_service_is_down_or_slow` |
| Duplicate or out-of-order job events | Counted once; durations right in any order (at-least-once SQS, confirmed by Mariam on #109) | 🧪 Tested, including a recording of what job-service sends | | `monitoring/job-events-monitor/tests/` |
| Portal when the gateway or a service is down | Clear message, retries with back-off (alerts 10 s → 60 s), never another project's or job's data | 🧪 Tested (portal unit tests, Chrome checks with FIXTURE pages) | | `portal/test/`, #96, #98, #100, #117 |
| Restarting containers keeps data | Datasets, models, experiments and job records still there after `make down && make up` | ✅ Measured locally: projects and datasets (19 Nov, `f8d8dab`); all 20 projects, 6 jobs with their status, 25 dataset records and the MLflow experiment list (21 Nov, `b404125`). ⏳ Models and MLflow runs: none exist until real training (#93) | **Records (PostgreSQL): kept**: identical lists before and after (projects, jobs and their status, datasets, MLflow experiments). **Files (LocalStack S3): lost**, the download answers 503, as [decision 0005](decisions/0005-localstack-for-s3.md) says (free LocalStack keeps S3 in memory; real S3 in the cloud is not affected). On 19 Nov the answer was a misleading 503 "Object storage is not reachable" (#126); since #142 (Faisal, 22 Nov) it is 404 `DATASET_FILE_MISSING` | [`docs/evaluation/test-b-restart-keeps-data.md`](evaluation/test-b-restart-keeps-data.md) |

## 3. Scalability

| What | Status | Result | Evidence |
|---|---|---|---|
| What scales separately and how (training workers vs inference vs stateless services behind the gateway) | ⏳ Write-up after the integrated run | | `docs/ARCHITECTURE.md` |
| 1 GPU vs 2-GPU DDP: speedup, efficiency, throughput, GPU-hours | ⏳ Waiting on: Ahmed + Abdulla, 2-GPU run (Tue 24). Only real GPU measurements are used | | `docs/BENCHMARKS.md` section 2 |
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
| Cost per job and per project | 🧪 Portal views on `main` (#117), tested with FIXTURE jobs. ⏳ Real numbers waiting on: machine types from the scheduler (#105) and real jobs (#93) | | `portal/components/usage/`, `portal/test/usage.test.mjs` |
| Cost of the 1 GPU vs 2 GPU benchmark | ⏳ Waiting on: Ahmed + Abdulla | | `docs/BENCHMARKS.md` |
| Total cloud spend | **$0: no AWS account.** The team uses the AWS Emulator (decision 0011), so all costs in this report are **estimates of what the same work would cost on AWS**, not bills | | [decision 0011](decisions/0011-aws-emulator-instead-of-aws-account.md) |
| Keeping cost down | ✅ Checked in the code (20 Nov, `main` at `474a732`). **1. Smallest machine that fits:** the scheduler picks 0 GPU → `c6i.2xlarge`, 1 → `g4dn.xlarge`, 2–4 → `g4dn.12xlarge`, 5–8 → `g4dn.metal` (`scheduler/app/machines.py`, #105); locally always `local-cpu` ($0). **2. Machines are not started and stopped per job:** each GPU pool has a fixed size set in Terraform (`worker_desired_capacity`, 1 in the dev settings; the 4-GPU pool 0; min 0), with no autoscaling, so a machine costs money while idle: one idle `g4dn.xlarge` ≈ **$12.62 a day** (24 h × $0.526). Saving money is manual: set the capacity to 0 when nobody trains, `terraform destroy` after use. **3.** The scheduler frees a job's slot only when the next job needs one ("Busy workers" stays 1 after a job); that affects placement, not the bill | | `scheduler/app/machines.py`, `infrastructure/main.tf`, `infrastructure/README.md` ("Demo 4"), `contracts/pricing.yaml` |

## 5. Observability (monitoring)

| What | Status | Evidence |
|---|---|---|
| Every service serves `/health` and `/metrics` | ✅ On `main` (shared service helper) | `*/app/common.py` |
| `job-events` read by exactly one reader, metrics per attempt | 🧪 Tested (24 tests). ✅ Runs in Compose (#115, merged 22 Nov): Healthy in CI (`make up`, and the Real login job) and on a laptop, 20 Nov | #115 |
| Dashboard "CloudTrain overview", 5 alert rules | ✅ Seen working on a laptop (20 Nov, #115 at `3fbdf42`): all 10 services UP, 0 alerts firing, time since the last `job-events` read 0–20 s (the 20 s long poll; alert at 120 s). Job, queue and GPU panels say "No data yet" until a training job runs (#93). This first run found two display bugs (a "56 years" spike before the first read, a 10000% axis), fixed in `3fbdf42`. 🧪 Alert rules unit-tested with promtool | `monitoring/README.md` |
| AWS side: CloudWatch dashboard and alarms in Terraform | ⏳ #134 (Fatma): log groups and 3 alarms, which match `monitoring/aws/README.md` (reviewed 20 Nov); the dashboard and the monitor-down alarm follow #115. On the emulator: setup only, no live data | #134 |

## 6. Limitations

- **No real cloud.** The AWS Emulator checks the infrastructure but runs no machines (decision 0011), so
  there is no measured cloud latency, cloud GPU performance or real bill.
- **GPU numbers come from one workstation**, not from the machine types priced in `contracts/pricing.yaml`.
- **Laptop timings** include Docker on a laptop and are not production numbers.
- **Test A covers 5 services** (projects, datasets, jobs, models, MLflow). Not tested: `predict` and the
  upload routes, which wait up to 300 s (`GATEWAY_UPLOAD_TIMEOUT_SECONDS`) before 503.
- **Locally, uploaded files do not survive a restart** (Test B, decision 0005): after `make down` +
  `make up`, datasets must be uploaded again. For the demo: no restart between uploading and showing.
- **LocalStack serves both S3 and SQS on the laptop.** During the 500 MB uploads (Test C) the time since the
  last `job-events` read rose to about 55 s on the dashboard (normally 0–20 s), still under the 120 s alert.
  In the cloud, S3 and SQS are separate services.
- `job-events-monitor` keeps durations in memory: a restart forgets jobs in flight (counts are kept).
- Tensor and pipeline parallelism are not evaluated (`docs/BENCHMARKS.md`: never simulated).
- _To be completed with the results._

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
| B | What survives `make down` + `make up` (records yes, local S3 files no) | [`evaluation/test-b-restart-keeps-data.md`](evaluation/test-b-restart-keeps-data.md) |
| C | Gateway p50/p95, dataset upload and download speed | [`evaluation/test-c-speed-and-alert.md`](evaluation/test-c-speed-and-alert.md) |

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
| Adel | This report and its methods; Tests A, B and C on a laptop; the job-events reader, Prometheus alerts and Grafana dashboard (#115, contract #125); live job status and alerts (#96, #100), MLflow results (#98), cost views (#117) and the 1-GPU vs multi-GPU comparison (#124) in the portal. Problems found and reported while measuring: #126 (Faisal), #138 (Maitha, fixed in #139) |
| Hilal | Portal pages and the browser walk-through used for the end-to-end timings |
| Ahmed + Abdulla | GPU benchmarks (`docs/BENCHMARKS.md`) |
| Mariam | Job timings, retries and cost fields (Training Jobs) |
| Fatma + Hamda | The CloudWatch alarms and dashboard in Terraform (#134) |
| Everyone | `/metrics` in every service; the integrated runs |
