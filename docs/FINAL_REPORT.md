# CloudTrain: final technical report

**Editor:** Ali. Each owner writes their own section. Due **Fri 27 Nov 2026**.

> **27 Nov.** Sections 1, 2, 3.1, 4, 6, 7 and 8 are Ali's. Sections 3.2 to 3.10 are written by their
> owners. Every number comes from a real run or from `main` on 27 Nov.

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

For each: what it does, design, API, data, tests, how it integrates, what works.

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
### 3.3 Training job management (Mariam)
### 3.4 Training engine and MLflow (Abdullah)
### 3.5 Distributed training and parallelism (Ahmed + Abdulla)
### 3.6 Terraform and cloud infrastructure (Hamda + Fatma)
### 3.7 Scheduling and compute (Maitha)
### 3.8 Model registry, deployment and inference (Majed)
### 3.9 CI/CD and security (Salem)
### 3.10 Portal, observability and evaluation (Hilal + Adel)

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
   one setup.
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

**The project in numbers (on 27 Nov):** 137 commits on `main` since 12 Nov, 80 merged pull requests,
89 issues (84 closed), 7 CI workflows.
