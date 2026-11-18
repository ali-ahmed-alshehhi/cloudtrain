# Evaluation: performance, reliability and cloud cost

**Owners:** Hilal + Adel (Student 10). **Status on 18 Nov 2026: skeleton.** The methods are fixed; most
numbers wait for the integrated system (see "Waiting on" in each table). Final version: Fri 27 Nov.

**How to read the status column**

| Mark | Meaning |
|---|---|
| ✅ Measured | A real number from the integrated system or a real GPU run, with the file or log it comes from |
| 🧪 Tested | The behaviour is checked by an automated test (often with a fake clock or FIXTURE data). It shows the logic is right, **not** how long it takes in the running system |
| ⏳ Not measured yet | Method fixed, number pending. "Waiting on" names who or what |

No number in this report is invented, estimated by hand or taken from FIXTURE data. Simulated or emulated
results are always labelled as such (decision 0011: AWS Emulator, no AWS account).

## 0. Setup

| | Value |
|---|---|
| Where everything runs | Docker Compose on a laptop (`make up`): 12 containers, i.e. the 9 CloudTrain services plus Postgres, LocalStack (S3, SQS) and MLflow |
| "Cloud" | The AWS Emulator with the same Terraform (decision 0011, #112): checks the infrastructure, runs no real machines |
| GPUs | Real GPU runs only on a team workstation (Ahmed + Abdulla, `docs/BENCHMARKS.md`). No cloud GPU |
| Monitoring | Prometheus + Grafana dashboard "CloudTrain overview" and `job-events-monitor` (`monitoring/`, #115, #109) |
| Versions | Recorded with each measurement (Git commit, `docker compose version`, Python, Node 24, PyTorch for GPU runs) |
| Repeats | Every timing is repeated at least 3 times; the report gives the median and the spread |

## 1. Performance

| What | Method | Status | Result | Evidence |
|---|---|---|---|---|
| Gateway latency per route, p50 / p95 | Prometheus histogram `gateway_request_duration_seconds` while `make e2e` runs 3 times; dashboard panel "Slowest 5% of answers" | ⏳ Waiting on: #115 in Compose, #99 merged | | |
| Time from `POST /jobs` to RUNNING (queue + scheduling) | `cloudtrain_job_queue_wait_seconds` from `job-events-monitor` (QUEUED → RUNNING per attempt), 10 small jobs | ⏳ Waiting on: #115, a real worker (#93) | | |
| Training time per job | `cloudtrain_job_run_seconds{result}` and MLflow run duration, same 10 jobs | ⏳ Waiting on: #93 | | |
| Alert delay: status change → visible in the portal | `occurred_at` of the event vs the time the alert appears in the browser (Playwright), plus `cloudtrain_job_event_lag_seconds` for the monitor | ⏳ Waiting on: #99 + job page (#59) | | |
| Inference latency `POST /predict` | 100 requests through the gateway after one warm-up; p50 / p95 | ⏳ Waiting on: Majed (prediction API, due Tue 24) | | |
| Dataset upload / download speed | Upload and download a 50 MB and a 500 MB file through the gateway, 3 times each, MB/s | ⏳ Waiting on: #99 (upload page) | | |

## 2. Reliability

| Scenario | Expected behaviour | Status | Result | Evidence |
|---|---|---|---|---|
| Worker killed mid-job | Heartbeat stops → FAILED after the timeout (120 s, 6 s in the demo settings) → retried → SUCCEEDED; time to detect and time to recover | 🧪 Tested in job-service (fake clock). ⏳ Integrated run waiting on: Mariam + Maitha (Sat 21 – Tue 24) | | `job-service/tests/test_recovery.py`, `tests/integration/test_failure_recovery.py` (skipped until then) |
| Retries used up | FAILED for good and reported to the dead-letter queue; dashboard alert `CloudTrainDeadLetters` | 🧪 Tested (job-service, alert rule) | | `test_retries_used_up_stays_failed_and_reports_to_the_dlq`, `monitoring/prometheus/alerts.test.yml` |
| A service stopped or too slow | The gateway answers 503 in the shared error format, nothing hangs; alert `CloudTrainServiceDown` after 1 min | 🧪 Tested (gateway, alert rule). ⏳ Each service stopped in Compose: after #115 | | `gateway/tests/test_gateway.py::test_503_when_a_service_is_down_or_slow` |
| Duplicate or out-of-order job events | Counted once; durations right in any order (at-least-once SQS, confirmed by Mariam on #109) | 🧪 Tested, including a recording of what job-service sends | | `monitoring/job-events-monitor/tests/` |
| Portal when the gateway or a service is down | Clear message, retries with back-off (alerts 10 s → 60 s), never another project's or job's data | 🧪 Tested (portal unit tests, Chrome checks with FIXTURE pages) | | `portal/test/`, #96, #98, #100, #117 |
| Restarting containers keeps data | Datasets, models, experiments and job records still there after `make down && make up` | ⏳ Waiting on: #99, #93 | | |

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
never $0 (#108, #114). Prices: `contracts/pricing.yaml`, real us-east-1 on-demand prices (#111).

| What | Status | Result | Evidence |
|---|---|---|---|
| Cost per job and per project | ⏳ Waiting on: #111, #114, #105 merged and real jobs (#93) | | Portal cost page (#117) |
| Cost of the 1 GPU vs 2 GPU benchmark | ⏳ Waiting on: Ahmed + Abdulla | | `docs/BENCHMARKS.md` |
| Total cloud spend | **$0: no AWS account.** The team uses the AWS Emulator (decision 0011, #112), so all costs in this report are **estimates of what the same work would cost on AWS**, not bills | | #112 |
| Keeping cost down (as designed) | GPU machines only while a job runs (scheduler frees the slot), smallest machine that fits the GPU count, `terraform destroy` after use | ⏳ Confirm once #105 is merged | |

## 5. Observability (monitoring)

| What | Status | Evidence |
|---|---|---|
| Every service serves `/health` and `/metrics` | ✅ On `main` (shared service helper) | `*/app/common.py` |
| `job-events` read by exactly one reader, metrics per attempt | 🧪 Tested; ⏳ in Compose after #109 order is agreed | #115 |
| Dashboard "CloudTrain overview", 5 alert rules | 🧪 Every query run against a live Prometheus 3.5.0; alert rules unit-tested. ⏳ First visual check after #115 is in Compose | `monitoring/README.md` |
| AWS side: CloudWatch dashboard and alarms in Terraform | ⏳ Waiting on: Hamda + Fatma (#109 item 2). On the emulator: setup only, no live data | |

## 6. Limitations

- **No real cloud.** The AWS Emulator checks the infrastructure but runs no machines (decision 0011), so
  there is no measured cloud latency, cloud GPU performance or real bill.
- **GPU numbers come from one workstation**, not from the machine types priced in `contracts/pricing.yaml`.
- **Laptop timings** include Docker on a laptop and are not production numbers.
- `job-events-monitor` keeps durations in memory: a restart forgets jobs in flight (counts are kept).
- Tensor and pipeline parallelism are not evaluated (`docs/BENCHMARKS.md`: never simulated).
- _To be completed with the results._

## 7. How to reproduce

```bash
make up && make e2e                      # integrated run; Prometheus and Grafana collect the numbers
open http://localhost:3001               # dashboard "CloudTrain overview" (after #115 is in Compose)
cd monitoring/job-events-monitor && python -m pytest
cd monitoring/prometheus && promtool test rules alerts.test.yml
cd portal && npm test
```
Exact commands and result files for each measurement are added next to its row when it is measured.

## 8. Contributions

| Who | Part of this evaluation |
|---|---|
| Adel | Methods, monitoring (`monitoring/`), cost views, reliability tests of the portal and job-events reader, this report |
| Hilal | Portal pages and the browser walk-through used for the end-to-end timings |
| Ahmed + Abdulla | GPU benchmarks (`docs/BENCHMARKS.md`) |
| Mariam | Job timings, retries and cost fields (Training Jobs) |
| Everyone | `/metrics` in every service; the integrated runs |
