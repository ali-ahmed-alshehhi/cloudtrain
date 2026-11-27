# CloudTrain: final technical report

**Editor:** Ali. Each owner writes their own section. Due **Fri 27 Nov 2026**.

> **27 Nov.** Sections 1, 2, 3.1, 4, 6, 7 and 8 are Ali's. Sections 3.2 to 3.10 were drafted from each
> owner's README, code, tests and merged pull requests; each owner checks their own. Every number comes
> from a real run or from `main` on 27 Nov.

## 1. The key question

*How do we turn an ML training script into a scalable, automated, reliable and reusable cloud ML service?*

A training script on one laptop works for the person who wrote it. As a shared service it falls short in
six places, and CloudTrain answers each one with a specific part of the system:

| A plain script... | What CloudTrain does instead | Where |
|---|---|---|
| cannot be shared safely: anyone with the file sees all the data | Users log in, work inside projects, and every service checks project membership | Gateway login (`gateway/app/auth.py`), Projects service, decision 0006 |
| keeps a terminal open for hours | `POST /jobs` answers 202 at once; the job waits on a queue and runs on a worker | Training Jobs, SQS `training-jobs`, Scheduler |
| loses the work when the machine dies | Workers send heartbeats; a job with no heartbeat fails and is retried | Training Jobs watchdog, decision 0007, `test_failure_recovery.py` |
| scales as one block | Each capability is its own service and scales alone: inference on CPU, training on GPU workers | Decision 0001, section 15 of `ARCHITECTURE.md` |
| leaves no record of what was trained on what | Datasets are versioned with checksums, every run is in MLflow with its dataset version, and models are registered from runs | Datasets, MLflow, Model Registry |
| is deployed by hand | Terraform creates every cloud resource; CI tests, scans and deploys every change | `infrastructure/`, `.github/workflows/` |

The short answer: microservices give each concern one owner and one contract, the cloud gives machines on
demand, distributed training uses more than one device for one job, and DevOps (infrastructure as code,
CI/CD, monitoring) keeps all of it repeatable.

## 2. Architecture

Full design: [`docs/ARCHITECTURE.md`](ARCHITECTURE.md). Diagrams:
[`docs/diagrams/architecture.svg`](diagrams/architecture.svg) and
[`docs/diagrams/deployment.svg`](diagrams/deployment.svg) (redraw with `python docs/diagrams/build.py`).

### 2.1 Services

CloudTrain has 10 services and a portal, built by 13 students in 10 groups:

| Service | Owner(s) | Port |
|---|---|---|
| API Gateway | Ali | 5810 (published) |
| Projects | Ali | 8001 |
| Datasets | Faisal | 8002 |
| Training Jobs | Mariam | 8003 |
| Scheduler | Maitha | 8004 |
| Training worker, with DDP | Abdullah; Ahmed + Abdulla | 8010 (local only) |
| MLflow | Abdullah | 5000 |
| Model Registry | Majed | 8006 |
| Inference | Majed | 8007 |
| Job events monitor, Prometheus, Grafana | Hilal + Adel | 8011, 9090, 3001 (laptop only) |
| Web Portal | Hilal + Adel | 3000 (published) |

Terraform infrastructure is Hamda + Fatma's; CI/CD, login and security are Salem's.

The brief asks for 8 logical services. Seven map to one service each. Notification has no container of its
own: Training Jobs publishes every status change, the portal shows them as alerts and the monitor turns
them into metrics (decision 0002).

### 2.2 Rules every service follows

- **One front door.** Only the gateway (5810) and the portal (3000) are published. The portal calls only
  the gateway. Services call each other's APIs and never read another service's database.
- **Contracts first.** Every API is an OpenAPI file in `contracts/`. Contract tests (Schemathesis, about
  3,000 generated requests) check that each running service answers as its file says.
- **Long work is asynchronous.** Training is queued; nobody holds a request open while it runs.
- **Same shape everywhere.** One error format with a `request_id`, `/health` and `/metrics` on every
  service, one JSON log line per request, settings only from environment variables.

### 2.3 How a training job flows

1. The portal sends `POST /api/v1/jobs` to the gateway. The gateway checks the token, adds `X-User-Id` and
   `X-Request-Id`, and forwards to Training Jobs.
2. Training Jobs checks project membership and the dataset version, saves the job and its queue message
   in one transaction (outbox), answers 202, then sends the message to SQS `training-jobs`.
3. The Scheduler is the only reader of that queue. It picks a machine type from the job's GPU count, checks
   capacity (a full scheduler leaves the message on the queue), reports `SCHEDULED`, and hands the job
   to a worker.
4. The worker downloads the dataset version through a time-limited S3 link, trains, logs to MLflow, and
   sends a heartbeat every 30 seconds.
5. With no heartbeat for 120 seconds, Training Jobs marks the attempt `FAILED` and queues a retry while
   the retry limit allows. After the limit, the job stays `FAILED` and a report goes to the dead-letter
   queue.
6. Every status change goes to `job-events` and into the job's history. The portal's alert feed and the
   monitor read them.
7. Majed's Model Registry registers a model from the run. Before a version goes live, Inference loads it
   and checks it can predict; a version that fails never takes traffic.

### 2.4 Data and cloud

Each service has its own PostgreSQL schema. Datasets and model files are in S3, queues in SQS. On AWS the
gateway, portal and services run on ECS Fargate behind a load balancer, training workers on EC2 in Auto
Scaling groups (decision 0012), the database on RDS, and logs and alarms in CloudWatch. We had no AWS
account: Terraform applies all of it to the AWS Emulator, and CI does the same on every change
(decision 0011). Section 6 lists what that means for our results.

## 3. Each subsystem (one section per student)

For each: what it does, design, API, data, tests, how it integrates, what works. Test counts are test functions
on `main` on 27 Nov.

### 3.1 Gateway, Projects and integration (Ali)

**What it does.** The gateway is the platform's only API entrance. The Projects service holds projects and
members and answers one question for every other service: is this user a member of this project? The
integration tests run the demo walk-through through the gateway against the whole system.

**Design.**
- The gateway has no database and no queue. It reads its route table (`gateway/app/routes.yaml`) and
  environment variables, so it can run as several copies behind the load balancer.
- On each request it verifies the login token, adds `X-User-Id` and `X-Request-Id`, and streams the
  request to the target service with a 10-second timeout (300 seconds for uploads). A service that is down
  or too slow gives 503 in the shared error format, so the portal never waits on a hung request.
- Any path containing `/internal/` gives 404 at the gateway, so internal endpoints cannot be reached from
  outside.
- Login has one function, `verify_token()`. Laptops and CI use a fixed dev token; the cloud checks
  Cognito ID tokens (RS256, issuer and audience). The gateway refuses to start with the dev token unless
  `ENVIRONMENT=local`.
- MLflow has no idea of projects. The gateway exposes it read-only (GET, plus POST only on `/search`) and,
  since #107, filters runs by the `project_id` tag: a user only sees runs of their own projects, and a run
  of another project gives 404.
- Projects stores `projects`, `members` and `idempotency_keys` in its own schema, with Alembic migrations.
  `POST /projects` honours `Idempotency-Key`, so a retried request does not create a second project.

**API.** Gateway: `/health`, `/metrics` and the forwarded `/api/v1/*` routes. Projects: `POST /projects`,
`GET /projects`, `GET /projects/{id}`, `POST /projects/{id}/members`, `GET /users/me`. Contracts:
`contracts/openapi/gateway.yaml` and `contracts/openapi/project-service.yaml`.

**Tests (on 27 Nov).**

| Where | Test functions | What they cover |
|---|---|---|
| `gateway/tests/` | 36 | Every route, the MLflow rewrite and project filter, 401 without a token, 503 when a service is down, `/internal/` blocked, request IDs, error format |
| `project-service/tests/` | 32 | The five endpoints, membership 200 / 403 / 404, idempotency, database down gives 503 |
| `tests/integration/` | 28 | The 12-step walk-through, failure recovery, refusals at submit time, the MLflow route against real MLflow |

`make e2e` runs the integration tests with the dev token; `make e2e-login` runs the same tests with real
Cognito login on the AWS Emulator, and CI runs both.

**Integration work.** Beyond my own services I wrote the architecture and contracts, reviewed the pull
requests that touch shared files, and kept the walk-through as the team's definition of "done": each step
stays skipped, with its owner's name, until that owner's work passes it on `main`.

**What works (on 27 Nov).** Every walk-through step passes on `main`. The last two were switched on on
26 and 27 Nov: step 7b, the machine is released after the job (#176, after Maitha's #161), and step 8,
single vs DDP through the platform (#177, after Ahmed + Abdulla's #172 and #173). CI runs the
walk-through twice: with the dev token, and with real Cognito login on the AWS Emulator. Every change to
the infrastructure also applies the whole dev environment to the emulator with Terraform (#6).

### 3.2 Datasets and storage (Faisal)

**What it does.** The Datasets service stores each dataset as a list of numbered versions. It checks the
file format on upload, keeps a SHA-256 checksum of every version, and lets only project members see or
download a dataset. Training workers get a time-limited link to one exact version.

**Design.**
- Metadata is in PostgreSQL schema `datasets` (tables `datasets`, `versions`, `lineage`, `audit_events`,
  `idempotency_keys`, from 3 Alembic migrations). Files are in S3 under `<dataset_id>/v<version>/data`:
  LocalStack on laptops (decision 0005), real S3 on AWS.
- A version is never changed. A new upload becomes version N + 1 with its own checksum, size and
  `storage_uri`; a database constraint keeps each (dataset, version number) pair unique.
- Uploads are checked against the declared format (`csv` needs a header row with a comma, `zip` and
  `tar_gz` must open), otherwise 400. They honour `Idempotency-Key`; the same key with a different file
  gives 409 `IDEMPOTENCY_KEY_REUSED`.
- Every request checks membership with the Projects service (403 for a non-member). Storage down gives
  503; storage up but the file gone (for example after a LocalStack restart) gives 404
  `DATASET_FILE_MISSING` (#142, after issue #126).
- Workers get a presigned S3 link that expires after 15 minutes, sent with the version's checksum.
  Lineage records which job used which version, once per job.
- An audit row is saved for every upload, new version, download and download link, in the same commit as
  the change, with the user and the request ID (#137). Refused or failed requests are not recorded.

**API.** Public, through the gateway: `POST /datasets`, `GET /datasets?project_id=`, `GET /datasets/{id}`,
`POST /datasets/{id}/versions`, `GET /datasets/{id}/versions/{v}` and `.../versions/{v}/download`.
Internal: `GET .../versions/{v}/download-url`, `POST` and `GET .../versions/{v}/lineage`, and
`GET /internal/datasets/{id}/audit`. Contract: `contracts/openapi/dataset-service.yaml`, which covers
the public paths and `download-url`; the lineage and audit endpoints are described in the service README.

**Tests (on 27 Nov).**

| Where | Test functions | What they cover |
|---|---|---|
| `dataset-service/tests/` | 34 | csv, zip and tar.gz uploads with checksums, new versions, wrong format, members only, idempotency, download link, lineage, audit rows, storage or database down 503, missing file 404, answers against the contract |

The unit tests use SQLite and an in-memory store; the PostgreSQL and LocalStack path runs in `make e2e`.

**How it integrates.** The portal uploads through the gateway. Before it accepts a job, Training Jobs calls
`GET /datasets/{id}` and `GET /datasets/{id}/versions/{v}` to check that the dataset belongs to the job's
project and the version exists. The worker asks for the download link, checks the checksum after the
download, and records lineage. Besides its database and S3, Datasets calls only the Projects service.

**What works (on 27 Nov).** The service replaced its stand-in on 16 Nov (#91). It serves walk-through
step 3 (upload, version 1 with a 64-character checksum) and the dataset check in step 4, and the worker in
step 6 trains on the version the job names. On AWS only settings change: Terraform gives the ECS task a role
for the datasets bucket and a database secret. That setup has run only on the AWS Emulator, which runs no
containers (decision 0011).

### 3.3 Training job management (Mariam)

**What it does.** The Training Jobs service owns the life of every job, from `POST /jobs` to a final
status. It checks and stores the job form, puts it on the `training-jobs` queue, follows the status steps
reported by the Scheduler and the worker, and makes sure no job stays `RUNNING` forever. It trains nothing.

**Design.**
- Tables in schema `jobs`: `jobs`, `attempts`, `events`, `outbox`, `idempotency_keys`. Every queue
  message is saved in `outbox` in the same transaction as its change and sent after the commit; unsent
  ones are retried every 2 seconds (decision 0007). `POST /jobs` answers 202 even when SQS is down, while
  `/health` reports 503.
- The form follows `contracts/training-job.schema.json`, plus one rule checked in code: for `ddp`,
  `world_size` must equal `gpu_count`. A dataset from another project gives 422 `DATASET_NOT_IN_PROJECT`.
- Status steps follow `contracts/job-states.md`; a step out of order gets 409. A repeated `SCHEDULED`
  report for the same attempt answers 200 with no event (contract change #89, found in the live
  failure-recovery run on 15 Nov).
- A watchdog runs every 10 seconds and fails a `RUNNING` job with no heartbeat for 120 seconds (one is
  sent every 30) or past its `max_runtime_minutes`. A report from an earlier attempt's worker gets 409
  `STALE_WORKER`, so a worker declared dead cannot finish the retry.
- A failed job goes back to `QUEUED` (`job.retrying`, attempt + 1) while `retry_limit` (0 to 5) allows,
  then stays `FAILED` with a report on `training-jobs-dlq`. The service also reads that queue and
  re-queues a stuck job at most 3 times: a `QUEUED` job, and since #168 a `SCHEDULED` job no worker took.
- GPU-hours are `gpu_count` x hours and the cost is the machine's price in `contracts/pricing.yaml`
  x hours, both summed over every attempt, since a failed attempt still used its machine (decision 0007).
  A machine with no price gives a `null` cost, never 0 (#114).

**API.** Public: `POST /jobs` (202), `GET /jobs?project_id=`, `GET /jobs/{id}`, `POST /jobs/{id}/cancel`,
`GET /jobs/{id}/events`, and the alert feed `GET /jobs/events?after=&project_id=&limit=`. Internal:
`GET /internal/jobs/{id}` for the Scheduler (#102), `POST /internal/jobs/{id}/status` and `.../heartbeat`.
Contracts: `contracts/openapi/job-service.yaml`, `contracts/training-job.schema.json`,
`contracts/job-states.md` and `contracts/events/job-event.schema.json`.

**Tests (on 27 Nov).**

| Where | Test functions | What they cover |
|---|---|---|
| `job-service/tests/` | 89 | Submit checks, status steps and 409s, cancel, heartbeats, stale worker, silent worker and time limit, retries, the dead-letter reader, cost over attempts, members only, alert feed, other services or the database down |
| `tests/integration/test_failure_recovery.py` | 1 | The real worker is killed mid-job; the job fails, is retried and succeeds |

Two of the 89 are parametrized, so pytest reports 93 tests.

**How it integrates.** The gateway forwards `POST /jobs`; the service asks Projects about membership and
Datasets about the version. The Scheduler is the only reader of `training-jobs` and reports `SCHEDULED`
and `RUNNING`; the worker sends heartbeats and the final status. Each change goes into the job's history,
the alert feed the portal reads, and the `job-events` queue the monitor reads.

**What works (on 27 Nov).** The service replaced its stand-in on 15 Nov (#90) and serves walk-through
steps 4, 5, 7 and 12 (the laptop job runs on the free `local-cpu` machine, so its cost is 0). Since #145
the failure-recovery test runs in CI on every pull request, with 2 s / 6 s heartbeat settings. A step
from `QUEUED` or `SCHEDULED` to `FAILED` was declined in #89, and costs are estimates, not an AWS bill.

### 3.4 Training engine and MLflow (Abdullah)

**What it does.** The training worker runs one job at a time: it downloads the exact dataset version,
trains, sends heartbeats, logs to MLflow and reports one final status. It trains two models: ResNet-18 on
CIFAR-10 archives and a small MLP (`tabular_mlp`) on one numeric CSV. MLflow is the official tracking
server, configured but not modified, and holds every run.

**Design.**
- `training/app/runtime.py` trains in one thread and supervises from another: a heartbeat every
  `HEARTBEAT_INTERVAL_SECONDS` (30 by default) and the job's `max_runtime_minutes`. A `CANCELLED` answer
  stops the work with no final report; otherwise it sends exactly one `SUCCEEDED` or `FAILED`.
- `dataset.py` gets the download link, streams the file with a size limit (10 GiB by default), checks the
  SHA-256 checksum and extracts zip or tar safely: absolute paths, `..`, links and devices are refused.
- `tracking.py` opens one MLflow run per attempt, tagged with `job_id`, `project_id`, `dataset_id`,
  `dataset_version`, `model`, `strategy`, `world_size` and software versions. It logs parameters, metrics
  per epoch, final metrics, and a PyTorch model at artifact path `model`, the format decision 0010 serves.
- `artifacts.py` writes S3 checkpoints, each object before the `latest` and `best` manifests, then the
  final bundle and a `final` manifest. A run resumes only from a checkpoint whose 7 compatibility fields
  all match (schema version, job, model, dataset checksum, hyperparameters, strategy, world size).
- Wisconsin Breast Cancer (decision 0008, `tabular.py`): a seeded stratified split, standardization from
  training rows only, and loss, accuracy and macro F1. The bundle keeps feature order, statistics, class
  labels and input schema. Seeding targets repeatable runs on the same software and hardware.
- `trainer.py` has the seam DDP plugs into: a `single` job runs the training loop in one process, and a
  `ddp` job hands the same loop to `ddp.launch` from `training/distributed/` (section 3.5).
- MLflow (`mlflow/Dockerfile`) is the official `v3.18.0` image plus database, S3 and metrics libraries.
  Runs are in PostgreSQL schema `mlflow`, files in `s3://$ARTIFACTS_BUCKET/mlflow`.

**API.** Worker: `POST /internal/run` (202; a second job gets 409 `WORKER_BUSY`), `/health` and `/metrics`
(`contracts/openapi/training-worker.yaml`), taking the form in `contracts/training-job.schema.json`.
MLflow: its own REST API; the gateway exposes it read-only at `/api/v1/experiments/*` (section 3.1).

**Tests (on 27 Nov).**

| Where | Test functions | What they cover |
|---|---|---|
| `training/tests/` (5 files) | 24 | Heartbeats then success, cancel, time limit, failure reported once, busy 409, bad forms 422, checksum and safe extraction, lineage, checkpoint order and resume rules, tabular split and bundle, seeding, MLflow tags and model path |

The other 30 test functions in `training/tests/` cover DDP (section 3.5). The unit tests use fakes, so
they need neither S3 nor a live MLflow server.

**How it integrates.** The Scheduler hands a job to a worker with `POST /internal/run`; in the cloud the
workers are EC2 machines in an Auto Scaling group (decision 0012). The worker calls Datasets (link,
lineage), Training Jobs (heartbeat, status), MLflow and the `artifacts` bucket, and never reads a queue.
The Model Registry registers models from its MLflow runs.

**What works (on 27 Nov).** The real worker replaced its stand-in on 22 Nov (#93). It serves walk-through
step 6 (the run is found by its job and project tags, with `model = tabular_mlp` and metrics) and step 9
(its model is registered), on an 8-row Wisconsin-style CSV for 1 epoch; step 8 uses the full 569-row
`training/distributed/data/wisconsin.csv`. The failure-recovery test runs this worker too. Laptops and CI
train on CPU only, and the AWS Emulator has no GPUs (decision 0011).

### 3.5 Distributed training and parallelism (Ahmed + Abdulla)

**What it does.** This part lets one training job run as several processes with PyTorch DistributedDataParallel
(DDP), and decides when that is worth it. It has no service of its own: the helpers in `training/distributed/`
run inside the training worker, and two tools measure `single` against `ddp`.

**Design.**
- `ddp.py` starts one process per GPU on one machine (`launch`), with NCCL between GPUs and gloo on a CPU. It
  refuses a job that needs more GPUs than the machine has, and one failed process stops the others. Each process
  reads its own share of the data, and the last incomplete batch is dropped so all take the same steps.
- DataLoader workers are forked. Real CIFAR-10 images showed that spawned workers cost about 2 s each to start;
  the fix took a 10-epoch run from 56.3 s to 24.9 s (`docs/BENCHMARKS.md`, section 3).
- In the worker (#172, issue #28), `training/app/trainer.py` runs a `ddp` job through `launch`, refuses one whose
  `world_size` differs from `resources.gpu_count`, and logs `epoch_seconds` and `epoch_images` every epoch.
- #179: the worker checks `ceil(training rows / world_size) ≥ batch_size` first and fails a smaller job with a
  one-line `DatasetTooSmall` reason. Without it a DDP process with no full batch divided by zero (step 8, #177).
- `selector.py` returns `single`, `ddp`, parallel trials or model parallelism, with a reason. It takes DDP on n
  GPUs only at 70% efficiency or more and within the GPU-hour budget; its sync overhead (10% per added GPU) and
  start-up (30 s) are assumptions until a 2-GPU run measures them.
- `platform_compare.py` (#173, issue #30) sends the same `tabular_mlp` job through the gateway as `single` and as
  `ddp` (2 processes) for seeds 0, 1 and 2, and tags each MLflow run with `result_label` (local stack only).

**API.** No endpoints. The interface is the job form (`contracts/training-job.schema.json`):
`parallelism.strategy` is `single` or `ddp`, and for `ddp` the `world_size` equals `resources.gpu_count` (at
most 8). Python: `ddp.launch(train, world_size)`, `select(Workload(...))`. Command line: `distributed.train`,
`distributed.benchmark` (`scaling`, `workers`, `report`) and `distributed.platform_compare`.

**Tests (on 27 Nov).**

| Where | Test functions | What they cover |
|---|---|---|
| `training/tests/test_distributed_ddp.py` | 11 | Single and 2-process DDP on a CPU, identical models, forked workers, too few GPUs refused, a failed process stops the others, CPU runs never reported as GPU scaling |
| `training/tests/test_distributed_worker.py` | 5 | Per-epoch metrics for both strategies, `world_size` ≠ `gpu_count` refused, no full batch gives a one-line reason |
| `training/tests/test_distributed_selector.py` | 4 | The rules and the job form they lead to, slow gradient sharing, the `world_size` limit, impossible workloads |
| `training/tests/test_distributed_metrics.py` | 7 | Warm-up epoch left out, speedup, efficiency, GPU-hours and cost, runs that cannot be compared refused |
| `training/tests/test_distributed_platform_compare.py` | 3 | Both forms follow the contract and differ only in strategy, the arithmetic, fewer than 3 epochs refused |

**How it integrates.** Maitha's Scheduler places a `ddp` job on one machine and Abdullah's worker calls
`ddp.launch`; only the main process logs to MLflow and saves the model. Hilal + Adel's comparison page reads
`epoch_seconds`, `epoch_images` and `result_label`, and they closed the hand-off on 26 Nov after checking it (#76).

**What works (on 27 Nov).** #172 and #173 merged on 25 Nov, #179 on 27 Nov, and walk-through step 8 passes on
`main` (#177). Labelled "2 processes on CPU, local stack", `ddp` took 14.2 ms per epoch against 13.6 ms for
`single` (speedup 0.96), inside the 22% spread between seeds. No real 2-GPU run was measured: under decision 0011
there is no machine with 2 GPUs, so the 1 vs 2 GPU rows in `docs/BENCHMARKS.md` say "not measured". The only GPU
numbers come from one workstation with one GPU (CIFAR-10: 2.0 s per epoch, 74.0% accuracy).

### 3.6 Terraform and cloud infrastructure (Hamda + Fatma)

**What it does.** Terraform in `infrastructure/` creates every cloud resource from code: network, storage,
queues, image registry, database, login, permissions, GPU worker pools, the services on ECS and monitoring. With
no AWS account it is applied to the AWS Emulator (decision 0011); the same modules target real AWS with
`use_emulator = false`.

**Design.**
- `main.tf` wires 12 modules, most behind an `enable_*` switch; `environments/dev/emulator.tfvars.example` turns
  them on, so one `terraform apply` builds the dev environment (133 resources in CI on 27 Nov, 126 before #180).
- `bootstrap/` creates the state bucket once (versioned, encrypted, private, TLS only); the root module locks its
  state with `use_lockfile` (#112).
- S3 `datasets` and `artifacts`; SQS `training-jobs` (300 s visibility timeout, dead-letter queue after 3
  receives) and `job-events`; RDS PostgreSQL 17, private, encrypted, SSL forced.
- Workers (decision 0012): two EC2 Auto Scaling groups from one module, `gpu-1` (`g4dn.xlarge`, at most 2) and
  `gpu-4` (`g4dn.12xlarge`, 4 GPUs, at most 1), each behind an internal load balancer on port 8010 (#133). Their
  IAM role allows the two buckets and `job-events` only.
- Services (#135): ECS cluster `dev-cloudtrain`, one Fargate service per service behind a public load balancer
  (5810, 3000), each with its own least-privilege task role.
- Monitoring (#134): a log group per service and 3 CloudWatch alarms. A small Pulumi program above Terraform
  (decision 0013, #149) reads `terraform output -json` and creates one resource, the CloudWatch dashboard.
- Emulator gaps are worked around and written down: security groups off, no RDS schemas, image pinned (#178).

**API.** Terraform inputs and outputs. Inputs: the tfvars file, `use_emulator`, the `enable_*` switches and sizes
such as `worker_desired_capacity` (demo 4: `0 to add, 1 to change, 0 to destroy`). Outputs the team reads: bucket
names, queue URLs, `ecr_repository_urls`, `db_endpoint`, the Cognito `jwt_*` settings, `worker_urls` and
`gateway_url`. Prices: `contracts/pricing.yaml`. Runbook and the 7 demos: `docs/DEPLOYMENT_GUIDE.md`.

**Tests (on 27 Nov).** There are no test functions for Terraform. These checks validate it:

| Where | What runs | What it checks |
|---|---|---|
| `.github/workflows/terraform.yml`, job 1 | `terraform fmt -check`, `terraform validate` | Formatting and the wiring of every module, without the emulator |
| `.github/workflows/terraform.yml`, job 2 | Apply, output check, destroy on the AWS Emulator | The whole dev environment (133 added and 133 destroyed on 27 Nov), and 11 outputs the team relies on |
| `.github/workflows/security.yml`, job 4 | Checkov on `infrastructure/` | Blocks risky settings such as a public bucket; 53 checks are skipped in the code, each with a reason |
| By hand (`docs/DEPLOYMENT_GUIDE.md`) | The 7 demos (22 Nov), destroy on a copy workspace (23 Nov) | 126 created, demo 4 changed 1 resource, destroy left the state empty |

Salem added the Terraform workflow in #129. It runs on every pull request that touches `infrastructure/`.

**How it integrates.** Each service's cloud resources come from here: Faisal's buckets, Mariam's queues, Maitha's
`worker_urls` (read as `TRAINING_WORKER_URLS`) and the Cognito settings for Ali's gateway. Salem's pipeline
deploys images into the ECS services; Terraform ignores `task_definition` and `desired_count` after creation, so
a later apply does not roll a deploy back.

**What works (on 27 Nov).** The Terraform check is green on `main`. The destroy rehearsal ran on the copy
workspace `destroy-rehearsal`, and #171 wrote it into the guide; the real destroy waits until after submission.
Limits (decision 0011): the emulator creates the resources but runs no containers and no machines, so the ECS
services run 0 tasks, the GPU pools train nothing, and the alarms and dashboard get no live data.

### 3.7 Scheduling and compute (Maitha)

**What it does.** The Scheduler is the only reader of the SQS queue `training-jobs`. For each job it picks a
machine type from the GPU count, checks capacity, reports `SCHEDULED` to Training Jobs, hands the job to a
worker, reports `RUNNING` and deletes the message. It runs on port 8004, internal only.

**Design.**
- One thread reads the queue with long polling (20 s), one message at a time (`scheduler/app/main.py`). Once a
  worker accepts the job (202) the message is deleted; from then on the worker's heartbeat protects the job.
- Machine choice (`app/machines.py`, #105): locally every job runs on `local-cpu`. In the cloud, 0 GPUs gets
  `c6i.2xlarge`, 1 gets `g4dn.xlarge`, 2 to 4 get `g4dn.12xlarge` and 5 to 8 get `g4dn.metal`, all priced in
  `contracts/pricing.yaml`. A 2-GPU DDP job therefore runs on the 4-GPU machine.
- Capacity (`app/capacity.py`): `CapacityTracker` limits running jobs to `SCHEDULER_MAX_WORKERS` (default 1) and,
  when set, GPUs to `SCHEDULER_MAX_GPUS`. A slot is freed when Training Jobs says the job ended or was put back
  for a retry, through `GET /internal/jobs/{id}` (contract change #102).
- #161 (issue #158): a job that arrived while the only worker was busy used to be turned away, and SQS hid it for
  the 300 s visibility timeout (3 small jobs took 732 s). Now, while every slot is busy, the Scheduler frees
  finished slots, and if none is free it waits 5 s without taking a message, so a waiting job does not use up
  its receives and land on the dead-letter queue. An empty queue also frees finished slots.
- A busy worker (409) is asked again every 5 s, up to 300 s. An unreachable worker or Training Jobs releases the
  slot and leaves the message on the queue. A 409 from Training Jobs means cancelled: slot released, message
  deleted.
- Routing (#131): `TRAINING_WORKER_URLS` maps each machine type to its pool's address (Terraform `worker_urls`).

**API.** No public endpoints. Its own: `GET /health` (200 when the queue is reachable) and `GET /metrics`
(`scheduler_jobs_placed_total`, `scheduler_workers_busy`, `scheduler_gpus_in_use`). It calls the worker's
`POST /internal/run` and Training Jobs' `POST /internal/jobs/{id}/status` and `GET /internal/jobs/{id}`.
Contracts: `contracts/openapi/scheduler.yaml` and `contracts/training-job.schema.json`.

**Tests (on 27 Nov).**

| Where | Test functions | What they cover |
|---|---|---|
| `scheduler/tests/test_standin.py` | 19 | Placing a job, a cancelled job dropped, the message kept when Training Jobs fails, slots freed on cancel, error, finish and retry, an unreachable worker, routing, no receive while full, the gauges |
| `scheduler/tests/test_capacity.py` | 10 | Reserve and release, full, a duplicate job, the GPU quota |
| `scheduler/tests/test_machine.py` | 6 | Local always `local-cpu`; cloud jobs with 0, 1, several and 8 GPUs |

**How it integrates.** Mariam's Training Jobs sends each job to `training-jobs` and records the Scheduler's
reports. Abdullah's worker runs the job and sends heartbeats; when they stop, Training Jobs queues a retry and the
Scheduler places it again. On AWS the Scheduler is an ECS service whose task role may only read `training-jobs`.

**What works (on 27 Nov).** Walk-through step 5 checks `job.queued`, `job.scheduled`, `job.running` and the
reported machine type. Step 7b checks that busy workers and GPUs in use are back to 0 after the job: Maitha wrote
it in #161 and it was switched on on 26 Nov (#176). After #161 a burst of 3 jobs took 13.2 s with no dead letters
(`EVALUATION.md`, Test F). Maitha rehearsed the failure demo on 26 Nov (issue #43): the worker was killed
mid-job, the job went `FAILED` on the heartbeat timeout and `SUCCEEDED` on attempt 2; CI runs the same case in
`tests/integration/test_failure_recovery.py`. Limits: jobs still run one at a time, since `SCHEDULER_MAX_WORKERS`
is not set in Terraform, and the cloud machine choice is only unit-tested (decision 0011: no real machines).

### 3.8 Model registry, deployment and inference (Majed)

**What it does.** The Model Registry registers a model version from a finished MLflow run, links it to its
job and dataset version, puts one version live (promote) and goes back (rollback). Inference answers
`POST /predict` with the live version. A version goes live only after Inference has loaded it and passed a
health check, so a failed deployment never replaces the healthy version.

**Design.**
- Register checks membership with Projects, then reads the run from MLflow: it must be `FINISHED`, hold a
  saved model and match the request's project, job and dataset tags (else 400). The same run twice gives
  409, and `Idempotency-Key` returns the first answer.
- The schema `registry` (`models`, `model_versions`, `releases`, `deployments`, `idempotency_keys`)
  decides which version is live; MLflow's `production` alias follows. Every promote or rollback attempt is
  saved in `deployments`, failed ones too.
- The health gate (#48, decision 0010): promote calls `POST /internal/models/{id}/candidates` on Inference,
  which loads the version and must get exactly one finite score per label for a fixed test image. A failure,
  or Inference out of reach, gives 503 `DEPLOYMENT_FAILED` and the live version stays. Rollback passes the
  same gate.
- Models are MLflow PyTorch models (`pickle`, or `pt2`); labels and image preparation come from the model's
  MLflow metadata, CIFAR-10 by default. Inference reads the files straight from S3 and runs on CPU, so
  MLflow stays out of the prediction path. The cost: an image of about 1.9 GB (decision 0010).
- Inference picks up a new live version within `INFERENCE_REFRESH_SECONDS` (default 10), or at once when
  the registry calls `.../refresh`. With the registry down it keeps serving the version it has.

**API.** Registry (8006): `POST /models`, `GET /models`, `GET /models/{id}/versions`,
`GET /models/{id}/production`, `POST /models/{id}/versions/{v}/promote`, `POST /models/{id}/rollback`.
Inference (8007): `POST /predict` (a PNG or JPEG up to 10 MB, top 3 labels) and `GET /model-info`.
Contracts: `contracts/openapi/model-registry.yaml` and `contracts/openapi/inference-service.yaml`.

**Tests (on 27 Nov).**

| Where | Test functions | What they cover |
|---|---|---|
| `model-registry/tests/` | 24 | Register from MLflow 2 and 3 style runs; bad runs (400); same run twice (409); idempotency; MLflow down (503); membership 403 / 404; promote through the gate; a failed deployment keeps the healthy version; Inference down; rollback and its gate; 401 |
| `inference-service/tests/` | 20 | The test CNN and a ResNet-18 saved as the worker saves it; candidate check and refusal; rollback; serving on with the registry down; no live version (503); bad image (400); 401; files read from S3 |

**How it integrates.** The registry calls Projects, MLflow and Inference; Inference calls only the
registry and S3. The portal's `/models` and `/predict` pages (#175) call both through the gateway. The
prediction API hand-off to Hilal + Adel (#77) was written up in #169.

**What works (on 27 Nov).** Both services, with the gate and rollback, landed in #97 (16 Nov). Walk-through
steps 9 to 11 went on in #150 (22 Nov): step 9 registers the job's own tabular run, step 10 shows the gate
refusing it and then promotes the small image model from `inference-service/app/fixture_model.py`, and
step 11 predicts `cat` for a synthetic cat image (section 6). Test G measured p50 3.2 ms, p95 4.4 ms. The
AWS Emulator runs no containers (decision 0011), so predictions are served only in the local stack.

### 3.9 CI/CD and security (Salem)

**What it does.** Seven GitHub Actions workflows take a change from a pull request to production: tests,
security scans, real login, Terraform, images, then staging and, after an approval, production. The
`security/` folder holds the real-login setup and tests, the security checks and the deployment policy.

**Design.**
- `ci.yml` (Ali's starter, extended in #78): lint and unit tests of changed services, Docker build,
  `make up`, contract tests and the walk-through. Its job `checks` is the required check on `main`.
- `security.yml` (#79), on every pull request and push, Mondays and on demand: Gitleaks over all of Git
  history, pip-audit and npm audit, Trivy on every image (blocks on a CRITICAL hole with a fix), Checkov on
  `infrastructure/`. Exceptions go in `security/SECURITY_CHECKS.md`; there are none.
- `login.yml` (#121) creates the Cognito pool, groups and test users on the AWS Emulator, runs CloudTrain
  with `AUTH_MODE=jwt`, then the 10 login tests and the walk-through with real ID tokens (decision 0006).
- `images.yml` (#122) builds the images (11 since #180), applies the same Trivy gate and pushes each to
  GitHub's registry as `<service>:<commit>`, never `latest`; the emulator's ECR refuses image uploads.
- `deploy.yml` (#151, #164): each ECS service gets a new task definition with only the image changed, then
  a smoke test runs those exact images with `make e2e`. Production gets the same images after Ali or Salem
  approves. Rollback is a manual run with `rollback` ticked: the previous images, the same approval, no
  rebuild.
- `terraform.yml` (#129) validates, applies the dev environment to the emulator and destroys it; #129 also
  added the GitHub OIDC deploy role. `assign-reviewers.yml` asks reviewers from `team.yml`.
- Workflows start at `contents: read` and store no cloud keys. Branch protection on `main`: 1 approval,
  code-owner review for shared files, branch up to date, no force pushes.

**API.** No endpoints. The interface is the workflow triggers (`.github/workflows/README.md`), the
`deploy.yml` inputs `commit` and `rollback`, and the gateway settings `AUTH_MODE`, `JWT_ISSUER`,
`JWT_JWKS_URL`, `JWT_AUDIENCE`. Refusals use `contracts/error-format.json`.

**Tests (on 27 Nov).**

| Where | Test functions | What they cover |
|---|---|---|
| `security/tests/` | 10 | A real Cognito token is accepted; 401 for no token, the dev token, a changed token, another key, an unsigned token, another app's token and an access token; another user's project refused |
| `.github/workflows/` | 7 workflows | Unit, contract and walk-through tests; 4 scanners; real login; Terraform apply on the emulator; the Trivy gate; the staging smoke test |

**How it integrates.** Every pull request passes CI and Security before review. The workflows use
Hamda + Fatma's Terraform and IAM roles, and Ali's walk-through as the smoke test; `login.yml` tests the
gateway's `verify_token()`.

**What works (on 27 Nov).** All seven workflows are on `main`. On 27 Nov commit `7c8faa8` passed staging
and went to production after approval. #151 included a rollback drill: all services to an older commit
and back. A new emulator release
refused our tokens on 25 Nov; Ali pinned version 1.0.604 (#178). Limits (decision 0011): ECS services run
no tasks, so a deploy changes the service records and the smoke test proves the images with Compose; the
load balancer has no HTTPS; roles are in the token, but no service checks them yet.

### 3.10 Portal, observability and evaluation (Hilal + Adel)

**What it does.** The portal (Next.js, port 3000) is the one web interface: projects, datasets, jobs with
live status and alerts, MLflow results, the single vs DDP comparison, usage and cost, models and
predictions. The monitoring stack turns `/metrics` and job events into a dashboard and 5 alert rules.
`docs/EVALUATION.md` (#119) measures the running system in Tests A to J.

**Design.**
- The portal calls only the gateway, through one client (`app/lib/gateway.mjs`); an unchanged retry
  reuses its `Idempotency-Key`. It is the notification service (decision 0002): it polls
  `GET /api/v1/jobs/events` every 5 to 10 seconds, with back-off.
- Hilal's pages: projects, datasets and alerts (#99); job submission, jobs list and live job page (#165);
  models, promote and rollback, and predictions (#175).
- Adel's parts: alerts and live badges (#96, #100), MLflow results (#98), cost per job and project (#117; a
  missing price shows "Price unknown", never $0), the comparison (#124) and the pages `/compare` and
  `/usage` (#156, #160, #166).
- `job-events-monitor` (8011) is the only reader of `job-events` (decision 0014). It ignores repeated
  `event_id`s, times each attempt in any event order, and exports `cloudtrain_job_*` metrics.
- Prometheus reads every `/metrics` every 15 s; its 5 rules: service down, server errors, dead letters,
  outbox backlog, job events not read. Grafana (3001, laptop only) has one generated dashboard (#115).
- For AWS, `monitoring/aws/` has a CloudWatch dashboard template and the monitor's IAM policy; Adel's #180
  makes the monitor its own ECS service in Terraform.

**API.** Portal pages `/`, `/jobs`, `/jobs/new`, `/jobs/{id}`, `/models`, `/predict`, `/compare`, `/usage`,
plus `/health` and `/metrics`, on the public gateway API and `contracts/events/job-event.schema.json`.
The monitor serves `/health` and `/metrics`; ports and settings in `contracts/ports.md` (#125).

**Tests (on 27 Nov).**

| Where | Test functions | What they cover |
|---|---|---|
| `portal/test/`, `portal/tests/` | 94 `test(` calls (97 runs) | Alert feed and back-off, comparison and cost arithmetic, gateway client and retry keys, job form, model records |
| `portal/tests/e2e/` | 8 `test(` calls | Playwright in Chrome: projects, datasets, jobs, models (fixture and live), `/compare`, `/usage` |
| `monitoring/job-events-monitor/tests/` | 27 | Duplicates and order, timings, invalid messages, CloudWatch lines, fake SQS |
| `monitoring/prometheus/alerts.test.yml` | 8 promtool cases | The alert rules |

**How it integrates.** The portal's alerts use the event feed that walk-through step 7 checks;
`/compare` and `/usage` show steps 8 and 12. The monitor reads the queue Mariam's Training Jobs writes.
The evaluation reported 4 problems, each fixed on `main`: #126 (#142), #138 (#139), #158 (#161), #167 (#168).

**What works (on 27 Nov).** From `EVALUATION.md`, on a laptop: 6 of 6 browser tests pass (Test I); alerts
appear 2.3 s (median) after the event, never more than 5.0 s (Test E); `/predict` p50 3.2 ms (Test G); a
killed worker is detected in about 5 s with short test settings (Test H); on Adel's laptop DDP on 2 CPU
processes was 1.50× faster per epoch, each job 0.7 s longer (Test J), against 0.96× in Ahmed + Abdulla's
run (section 3.5): with epochs this short the result depends on the machine. #175 then added the model pages, with 8 of 8 browser
scenarios passing. Limits: no GPU or AWS numbers (decision 0011), and the portal has no real sign-in yet
(it uses the dev token).

## 4. Engineering decisions and trade-offs

Every decision is in [`docs/decisions/`](decisions/), with its context, the options and the trade-offs.
In short:

| # | Decision | Main trade-off | Effect we saw |
|---|---|---|---|
| 0001 | Microservices behind one gateway | More network calls that can fail, so timeouts and 503s everywhere | 13 people built in parallel against written contracts |
| 0002 | Notifications are portal alerts from job events, no separate service | Alerts only in the portal, no email | No extra service to own |
| 0003 | Node 24 instead of Node 20 | None found | Node 20 had stopped getting security fixes in April 2026 |
| 0004 | Public GitHub repository | Anyone can read the code | Branch protection works on a free account; CI scans for secrets |
| 0005 | LocalStack S3 instead of MinIO on laptops | Local files are lost when LocalStack restarts | MinIO had stopped publishing free images; one container fewer |
| 0006 | Amazon Cognito for login | ID tokens only; users exist only in the cloud | Gateway code is plain OpenID Connect; laptops keep the dev token |
| 0007 | Training Jobs: outbox, one watchdog, stale-worker check, cost per attempt | `POST /jobs` answers 202 even when SQS is down (health shows 503) | The live failure-recovery run on 15 Nov found a repeated `SCHEDULED` report, fixed by contract change #89 |
| 0008 | Wisconsin Breast Cancer as the tabular use case | Reproducible only on the same software and hardware | Trains in seconds, so the full walk-through runs in CI |
| 0009 | LocalStack for Terraform practice | Superseded by 0011 | |
| 0010 | MLflow PyTorch models, served from S3, with a check before going live | Inference image about 1.9 GB; `pickle` models only from our own runs | A model that cannot predict never goes live (walk-through step 10) |
| 0011 | The AWS Emulator stands in for an AWS account | No real machines: no real GPU training, no running containers | No bill and no GPU quota wait; all Terraform demos run on a laptop and in CI |
| 0012 | Workers on EC2 in an Auto Scaling group | We start and stop machines by capacity, not per job | Worker count is one number in a tfvars file |
| 0013 | A small Pulumi layer above Terraform, for one dashboard | Two tools, two state files, destroy order matters | Answered the professor's request without touching the mandatory Terraform |
| 0014 | One job-events reader, Prometheus and Grafana, matching CloudWatch alarms | On AWS the monitor is an ECS service in Terraform (#180), which the emulator does not run | 5 alert rules, unit-tested with promtool |

The measured effect of 0007 and 0010, such as the time to detect a dead worker and to recover, is in
Hilal + Adel's evaluation (`EVALUATION.md`, #119).

## 5. Results
Benchmarks (`docs/BENCHMARKS.md`), evaluation (`docs/EVALUATION.md`), test results (`docs/TESTING.md`).

## 6. Limitations

- **No real AWS.** Everything cloud-side ran on the AWS Emulator (decision 0011). It creates the resources
  Terraform asks for, but runs no real containers on ECS and no real machines on EC2. We can show that the
  infrastructure is correct and repeatable, not how it performs on AWS.
- **No real multi-GPU scaling.** The emulator has no GPUs, so the 1 vs 2 comparison in walk-through step 8
  runs two CPU processes, and every result says where it ran. The GPU numbers in `BENCHMARKS.md` come from
  one workstation with one GPU. Ahmed + Abdulla's run through the platform (#30, 25 Nov) gave 14.2 ms per
  epoch for 2 CPU processes against 13.6 ms for one (speedup 0.96) on the 569-row Wisconsin data. With
  epochs this short it shows that DDP works end to end, not that it is faster.
- **Only two parallelism strategies.** The job form accepts `single` and `ddp`. Hyperparameter search,
  tensor and pipeline parallelism are not built.
- **The demo model is served as an image model.** `POST /predict` takes an image, so the tabular model from
  the walk-through fails inference's check and is never promoted; steps 10 and 11 serve a small
  CIFAR-10-shaped test model instead.
- **Emulator gaps.** Its RDS has no schemas (found on #66), so the schema bootstrap script only works on
  real AWS. Services keep the PostgreSQL from `make up` for their tables.
- **Local storage is not kept.** LocalStack keeps uploaded files and queue messages in memory; a restart
  loses them (decision 0005). PostgreSQL records are kept.
- **Alerts only in the portal.** No email or chat notifications (decision 0002).
- **Monitoring on AWS is only defined, not run.** The three CloudWatch alarms, the dashboard and, since
  #180, the job events monitor as its own ECS service all exist in Terraform. The emulator runs no
  containers, so the monitor's metrics have only been seen on laptops (decision 0014).
- **Cost is an estimate.** It uses AWS on-demand prices for us-east-1 copied on 17 Nov
  (`contracts/pricing.yaml`) and the hours each machine ran, not an AWS bill.

## 7. Lessons learned

1. **Write the contracts before the code.** With 13 people and two weeks, agreeing the APIs, the job form
   and the events up front is what let everyone build at the same time. Changes still happened
   (#89, #102, #125, #147), and each went through a Contract change issue that every affected owner
   agreed to.
2. **Run the failure, don't just test it.** The live failure-recovery run on 15 Nov found a case no unit
   test had: a repeated `SCHEDULED` report while the only worker was down (decision 0007). Later, a review
   of a proposed retry change found it could leave a job stuck in `QUEUED` through the dead-letter queue
   (#161), before it reached `main`.
3. **Security gaps sit between services.** Each service checked membership on its own data, but the MLflow
   route let any logged-in user read every project's runs, because MLflow has no projects. We only saw it
   by looking at the whole path, and fixed it at the gateway (#107).
4. **An emulator is not the cloud.** The AWS Emulator saved us an account and a bill, but it has gaps
   (no RDS schemas, no real machines). We learned to check its list of known gaps before blaming our
   code, and to say where every measurement ran.
5. **Free tools can disappear.** MinIO stopped publishing free images and Node 20 reached end of life
   while we were planning. Pinning versions and writing each switch down as a decision kept the team on
   one setup. The one tool we had not pinned bit us: on 25 Nov a new AWS Emulator release refused our
   real Cognito tokens and turned the Login check red overnight, with no change on our side. We pinned
   the last good version (#178).
6. **Keep `main` green.** One lint error on `main` made `make check` fail for everyone until it was fixed
   (#163). Because `main` only accepts up-to-date branches, every merge also sends the open pull requests
   back through CI, so merges have to be done in order.
7. **Plan the longest chain first.** Step 8 needs DDP in the worker (#28), then the comparison run (#30),
   then the comparison page (#76), each waiting on the one before. The chain finished two days after the
   plan: #28 and #30 merged on 25 Nov (#172, #173), Hilal + Adel checked the comparison page against
   those runs on 26 Nov (#76), and step 8 went green on 27 Nov (#177). Switching step 8 on also found a
   crash: on a small dataset a DDP process could get no full batch and divide by zero. Ahmed + Abdulla
   fixed it in #179.

## 8. Learning outcomes covered

| Outcome | Where CloudTrain shows it |
|---|---|
| Architecture and decomposition | 10 services and a portal, one owner each, mapped to the brief's 8 logical services (section 2, decision 0001) |
| REST and service communication | Versioned REST API behind one gateway; OpenAPI contracts in `contracts/`; contract tests with Schemathesis; internal calls listed in `ARCHITECTURE.md` section 7 |
| Databases, storage and messaging | A PostgreSQL schema per service; versioned datasets with checksums in S3; SQS queues with a dead-letter queue and an outbox |
| Docker | One image per service; the whole platform starts with `make up`; images scanned with Trivy in CI |
| Terraform | Every cloud resource in `infrastructure/`, remote state with locking, the seven mandatory demos on the AWS Emulator; CI applies the dev environment on every change |
| Cloud provisioning, networking, security and storage | VPC with public and private subnets, load balancer, ECS Fargate, EC2 Auto Scaling, RDS, S3, SQS, Cognito, Secrets Manager, least-privilege IAM per service |
| Distributed training | PyTorch DDP in `training/distributed/`, the parallelism selector, and the single vs DDP comparison through the platform (#172, #173; walk-through step 8) |
| CI/CD | Seven GitHub Actions workflows: tests, security scans, images, login, Terraform, deploy with approval for production; branch protection and required reviews |
| Model versioning, tracking and serving | MLflow runs tagged with project, job and dataset version; Model Registry with promote and rollback; Inference with a check before a version goes live |
| Observability, failure recovery, scalability and cost | JSON logs and `/metrics` everywhere, Prometheus alerts and Grafana, CloudWatch alarms; heartbeat, retry and dead-letter queue; services scale separately; GPU-hours and cost per job |

**The project in numbers (on 27 Nov):** 142 commits on `main` since 12 Nov, 85 merged pull requests,
89 issues (all closed), 7 CI workflows.
