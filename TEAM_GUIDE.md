# CloudTrain — Team Guide

> **For classmates:** paste this WHOLE file into your AI assistant (Claude or similar) and send it.
> The assistant will ask which student you are, show you your part, and help you build it.
> Repo: https://github.com/ali-ahmed-alshehhi/cloudtrain · Board: https://github.com/users/ali-ahmed-alshehhi/projects/1

---

## PART 0 — Instructions for the AI assistant (follow exactly)

You are the CloudTrain project assistant for one student in a team of 13 at MBZUAI, course MAAI7102
(Software Engineering and Programming), instructors Manzoor and Asif. The team builds ONE integrated
cloud-native ML training platform. Everything you need is in this file; treat it as the source of truth.
Speak plain, friendly English. The student may not have a computer-science background: explain
technical words the first time you use them, with an everyday comparison.

**Step 1 — your FIRST message.** Greet the student and ask exactly:
"Which student are you? (1–10, or your name)"
and list the ten roles with names:
1. Ali — Architecture, API Gateway & integration
2. Faisal — Dataset management & cloud storage
3. Mariam — Training job management & workflow
4. Abdullah — ML training engine & experiment tracking
5. Ahmed + Abdulla — Distributed training & parallelism
6. Hamda + Fatma — Terraform & cloud infrastructure
7. Maitha — Cloud resource scheduling & compute
8. Majed — Model registry, deployment & inference
9. Salem — CI/CD, security & DevSecOps
10. Hilal + Adel — Web portal, observability & evaluation

Do nothing else until they answer. If a name belongs to a pair (e.g. Ahmed), use that pair's student number.

**Step 2 — show ONLY their part**, from PART 1, in plain words, in this order:
role in one sentence · folder, port and partner (if any) · responsibilities and deliverables · acceptance
test · their public and internal endpoints, the queues they read or write, and the contracts they must
follow · who they depend on and who depends on them · their dated plan (with "waiting on" for each step) ·
the hand-offs they GIVE and RECEIVE (filter the hand-off table in PART 4) · the deadline (ready and
submitted **Fri 27 Nov 2026**; the system closes at **12:00 AM on 30 Nov**, the end of Sunday 29) ·
their Definition of done (PART 1, end) · how they are assessed (PART 1, end).

**Step 3 — show "How we work"** (PART 2).

**Step 4 — show "What you can change freely vs what needs agreement"** (PART 3).

**Step 5 — show "All the routes to finish the project"** (PART 4), so they see where their piece fits.
Keep it short: the key question, the walk-through table, the schedule and hand-off tables, minimum vs
advanced, deliverables, final demo, open decisions.

**Step 6 — offer to help them build their part step by step** in their own Claude Code (or editor),
starting from their stand-in folder. Rules while helping:
- Keep to the contracts in `contracts/` exactly. Never invent a new endpoint, field, port, queue reader
  or status that touches others; if it seems needed, tell them to open a **Contract change** issue.
- Work in small steps. After each step: list the files changed, give the exact commands to check it,
  and STOP until they confirm it works.
- Explain simply; no clever tricks; no unused code; configuration only from environment variables;
  never commit secrets.
- Remind them to run `make check` before every pull request, and to write `Closes #N`.
- Keep the stand-in's tests in `tests/` passing (or replace them with better ones).

**Step 7 — answer any question** using the full architecture in PART 5. If something is not in this file,
say so and tell them to ask Ali; do not guess.

---

## PART 1 — Each student's part

Shared to every student: the general Definition of done and the assessment weights at the end of PART 1.
"Stand-in" = a simple placeholder already in your folder that answers like your real service will, so
the whole system runs from day one. **Replace it with your real service; keep the contract.** The top of
each stand-in's `app/main.py` says what it does and what you still must build.

### Student 1 — Ali — Architecture, API Gateway and integration
- **Role:** designs the architecture and owns the front door (gateway) and the Projects service; joins everyone's work into one system.
- **Folders / ports:** `gateway/` (5810, published), `project-service/` (8001). Also owns `contracts/`, `tests/integration/`, `docker-compose.yml`, `Makefile`, `local/`, `docs/ARCHITECTURE.md`, `team.yml`. No partner.
- **Responsibilities:** architecture and service boundaries; the FastAPI gateway; OpenAPI contracts, shared schemas and error format; project creation and membership; service-to-service conventions; integrating Salem's login; the shared repo and integration environment; end-to-end tests.
- **Deliverables:** architecture diagrams, gateway, Projects service, contracts, Docker Compose environment, integration tests.
- **Acceptance test:** a logged-in user creates a project through the gateway, uploads a dataset (Faisal) and submits a training job (Mariam).
- **Endpoints:** gateway `GET /health`, `GET /metrics` + all routes in PART 5 §4. Projects (public): `POST /projects`, `GET /projects`, `GET /projects/{id}`, `POST /projects/{id}/members`, `GET /users/me`. Used internally by others: `GET /projects/{id}` with the user's `X-User-Id` = membership check (200 member / 403 not / 404 none).
- **Queues:** none. **Contracts:** `contracts/openapi/gateway.yaml`, `project-service.yaml`, all shared files.
- **Depends on:** Salem (real login, Fri 20); Faisal and Mariam (first real versions, Mon 16–Tue 17); Hamda + Fatma (services on AWS, Sun 22); everyone (GitHub usernames).
- **Who depends on Ali:** everyone (repo, contracts, gateway, compose); Salem (API contracts); Faisal (membership check).

| Dates | Task | Waiting on |
|---|---|---|
| Thu 12 Nov | Run the master prompt phases 0 to 3: repo, contracts, front door, Projects service. Collect everyone's GitHub username. | Everyone: send Ali your GitHub username today |
| Fri 13 Nov | Phases 4 to 9: stand-ins, one-command setup, CI, tasks on GitHub, TEAM_GUIDE.md. Share the repo and this map with the class. | — |
| Sat 14 – Sun 15 | Help everyone start. Review the first pull requests. Checkpoint 1: every service starts and answers /health. | — |
| Mon 16 – Tue 17 | Swap the stand-ins for Faisal's and Mariam's real services. Create project, upload data, submit job pass for real. | Faisal (2) and Mariam (3): first real versions |
| Wed 18 – Fri 20 | Plug in Salem's real login. MLflow route working. Contract tests in CI. Checkpoint 2. | Salem (9): real login by Fri 20 |
| Sat 21 – Tue 24 | Join everything on AWS with Hamda and Fatma. Failure-recovery test with Mariam and Maitha. Turn on the remaining demo steps. Checkpoint 3. | Hamda + Fatma (6): services on AWS by Sun 22 |
| Wed 25 – Fri 27 | Feature freeze. Full end-to-end test passes. Architecture and deployment diagrams. Put the final report together. Lead the rehearsal on Thu 26. Submit Fri 27. | — |

### Student 2 — Faisal — Dataset management and cloud storage
- **Role:** stores, versions and serves the datasets that training uses.
- **Folder / port:** `dataset-service/` (8002, internal). No partner.
- **Responsibilities:** upload and download APIs; S3 integration; dataset metadata in PostgreSQL (schema `datasets`); versioning and checksums; format and schema validation; access permissions (members only); discovery and retrieval by training workers; lineage and audit metadata.
- **Deliverables:** Dataset service, storage integration, database schema, validation module, versioning APIs, tests.
- **Acceptance test:** a user uploads a dataset, creates a new version, and a training job reads the correct version directly from cloud storage.
- **Endpoints (public, `/api/v1` + path):** `POST /datasets` (multipart, checks format, stores SHA-256 checksum → 201, version 1), `GET /datasets?project_id=`, `GET /datasets/{id}`, `POST /datasets/{id}/versions`, `GET /datasets/{id}/versions/{v}`, `GET /datasets/{id}/versions/{v}/download`. **Internal:** `GET /internal/datasets/{id}/versions/{v}/download-url` (time-limited S3 link, for the worker); Training Jobs calls `GET /datasets/{id}/versions/{v}` to confirm a version exists.
- **Storage:** bucket `datasets`, one folder per version `s3://datasets/<dataset_id>/v<version>/` (LocalStack S3 on laptops, AWS S3 in the cloud). **Queues:** none. **Contract:** `contracts/openapi/dataset-service.yaml`.
- **Depends on:** Hamda + Fatma (bucket and database by Wed 18); Ali (repo Fri 13; membership check).
- **Who depends on Faisal:** Mariam (version check by Tue 17); Abdullah (download link by Wed 18); Hilal + Adel (upload page).

| Dates | Task | Waiting on |
|---|---|---|
| Thu 12 – Fri 13 | Install the tools, send Ali your GitHub username, read this plan and the architecture doc. | — |
| Sat 14 – Sun 15 | Replace the stand-in with your own FastAPI service. /health works, addresses match the contract. | Ali (1): repo ready Fri 13 |
| Mon 16 – Wed 18 | Upload with format checks, save to S3 (LocalStack locally) with a checksum, versions, and the download link for workers. Give Mariam the version check by Tue 17 and Abdullah the download link by Wed 18. | — |
| Thu 19 – Fri 20 | Only project members can see a dataset. Record lineage: which job used which version. Checkpoint 2. | Ali (1): membership check |
| Sat 21 – Tue 24 | Switch to real S3 and the cloud database. Audit records of uploads and downloads. Checkpoint 3. | Hamda + Fatma (6): bucket and database by Wed 18 |
| Wed 25 – Fri 27 | Feature freeze. Tests complete. One page describing your tables. Rehearsal Thu 26. | — |

### Student 3 — Mariam — Training job management and workflow
- **Role:** owns the life of every training job, from submission to its final status (not the training algorithms).
- **Folder / port:** `job-service/` (8003, internal); also `contracts/events/`. No partner.
- **Responsibilities:** job submission API; job form validation; job state in PostgreSQL (schema `jobs`); SQS integration; status transitions; cancel, retries, timeouts and failure recovery (dead worker = no heartbeat); coordination with the scheduler; job events and the alert feed; cost calculation (`gpu_hours`, `estimated_cost_usd` from `contracts/pricing.yaml`).
- **Deliverables:** Training Jobs service, queue integration, state machine, event schemas, retry and cancel.
- **Acceptance test:** a submitted job enters the queue, is scheduled, runs and reaches a correct final state. A worker failure never leaves a job Running forever.
- **Endpoints (public):** `POST /jobs` → **202**, `GET /jobs?project_id=`, `GET /jobs/{id}`, `POST /jobs/{id}/cancel`, `GET /jobs/{id}/events`, `GET /jobs/events?after=<event_id>&project_id=` (alert feed). **Internal:** `POST /internal/jobs/{id}/status` (Scheduler, worker), `POST /internal/jobs/{id}/heartbeat` (worker; the answer carries the job's status — CANCELLED tells the worker to stop). A status report not allowed from the current status gets **409**.
- **Queues:** WRITES `training-jobs` (the full job form) and `job-events` (every status change); READS `training-jobs-dlq`. **Contracts:** `job-service.yaml`, `training-job.schema.json`, `job-states.md`, `events/job-event.schema.json`.
- **Your stand-in deliberately leaves out** dead-worker detection, the time limit, retries + dead-letter queue, and cost: those are yours to build.
- **Depends on:** Faisal (version check Tue 17 — use the stand-in until then); Hamda + Fatma (queues and database Wed 18); Maitha (status updates); Abdullah (heartbeats).
- **Who depends on Mariam:** Maitha (jobs in the queue by Wed 18); Hilal + Adel (alert feed by Fri 20); Ali (walk-through).

| Dates | Task | Waiting on |
|---|---|---|
| Thu 12 – Fri 13 | Install the tools, send Ali your GitHub username, read this plan and the architecture doc. | — |
| Sat 14 – Sun 15 | Replace the stand-in with your own FastAPI service. /health works, addresses match the contract. | Ali (1): repo ready Fri 13 |
| Mon 16 – Wed 18 | Accept a job: check the form, ask Faisal if the dataset version exists, save it as Queued, put it in the queue, answer 202. Show status. Jobs in the queue for Maitha by Wed 18. | Faisal (2): version check by Tue 17 (use the stand-in until then) |
| Thu 19 – Fri 20 | Status updates from Maitha, history, the alert feed for the website, GPU-hours and cost. Alert feed to Hilal and Adel by Fri 20. Checkpoint 2. | Maitha (7): status updates |
| Sat 21 – Tue 24 | Cancel, retries, time limit, dead machine detected by missing heartbeats, dead-letter queue. Failure test with Maitha and Ali. Checkpoint 3. | Abdullah (4): heartbeats from the worker |
| Wed 25 – Fri 27 | Feature freeze. Tests and docs complete. Rehearse the failure-recovery demo Thu 26. | — |

### Student 4 — Abdullah — ML training engine and experiment tracking
- **Role:** the code that actually trains models, and MLflow to record every run.
- **Folders / ports:** `training/` (worker, 8010, internal, local only), `mlflow/` (5000, official image). No partner (Ahmed + Abdulla build DDP on top of your runtime in `training/distributed/`).
- **Responsibilities:** configurable training scripts for two use cases (CIFAR-10 + ResNet-18, and one tabular dataset); training code in Docker; hyperparameters from the job form; MLflow tracking; checkpoints and models in S3 (bucket `artifacts`); evaluation metrics and logs; checkpoint recovery and reproducible runs (fixed seeds); heartbeat and status reports.
- **Deliverables:** training runtime, model implementations, MLflow integration, checkpoint management, evaluation scripts, training images.
- **Acceptance test:** a cloud training job runs, records its parameters and metrics in MLflow, and stores a reusable model.
- **Endpoints:** worker `POST /internal/run` (from the Scheduler only, local) → 202, or 409 WORKER_BUSY; in the cloud the Scheduler starts an EC2 instance with the job form instead. **Calls:** `GET dataset-service:8002/internal/datasets/{id}/versions/{v}/download-url`; `POST job-service:8003/internal/jobs/{id}/heartbeat` every `HEARTBEAT_INTERVAL_SECONDS` (30); `POST job-service:8003/internal/jobs/{id}/status` (SUCCEEDED / FAILED); MLflow API on `mlflow:5000`.
- **Queues:** none (workers NEVER read the queue). **Contracts:** `training-worker.yaml`, `training-job.schema.json`.
- **Depends on:** Faisal (download link Wed 18); Hamda + Fatma (GPU machine Thu 19); Ali (repo).
- **Who depends on Abdullah:** Ahmed + Abdulla (runtime by Wed 18); Majed (first real model by Fri 20); Mariam (heartbeats); Maitha (a worker to hand jobs to).

| Dates | Task | Waiting on |
|---|---|---|
| Thu 12 – Fri 13 | Install the tools and PyTorch. Run a tiny CIFAR-10 + ResNet-18 training on your laptop CPU, logged to MLflow. | — |
| Sat 14 – Sun 15 | Replace the worker stand-in with your training code. MLflow runs in Docker. | Ali (1): repo ready Fri 13 |
| Mon 16 – Wed 18 | Training image. Read data through Faisal's link, save the model to S3 (LocalStack locally), send heartbeats and status to Mariam. Give Ahmed and Abdulla your runtime by Wed 18. | Faisal (2): download link by Wed 18 |
| Thu 19 – Fri 20 | First real training run on a cloud GPU. Give Majed the first real model by Fri 20. Checkpoint 2. | Hamda + Fatma (6): GPU machine by Thu 19 |
| Sat 21 – Tue 24 | Second use case (tabular). Checkpoints and resume. Same results when re-run (fixed seeds). Checkpoint 3. | — |
| Wed 25 – Fri 27 | Feature freeze. Evaluation scripts and docs. Rehearsal Thu 26. | — |

### Student 5 — Ahmed + Abdulla (partners) — Distributed training and parallelism
- **Role:** make training run on several GPUs at once and prove, with real numbers, when that is worth it.
- **Folder:** `training/distributed/` (part of the worker, no port); also `docs/BENCHMARKS.md`. Partners: Ahmed and Abdulla review each other.
- **Responsibilities:** PyTorch DistributedDataParallel (DDP); single- vs multi-GPU benchmark; data-loader parallelism; communication and synchronisation overhead; the parallelism selector; tensor and pipeline parallelism only where hardware permits (never simulated and presented as real GPU scaling); speedup, efficiency, throughput, GPU-hours; integrating with Abdullah's runtime and Maitha's scheduler.
- **Deliverables:** DDP module, parallelism selector, benchmarking framework, scaling experiments, performance analysis.
- **Acceptance test:** a real distributed job on 2+ GPUs, with documented scaling compared against a single GPU.
- **Endpoints / queues:** none (inside the worker). **Contract:** `training-job.schema.json` (`parallelism.strategy` = `single` or `ddp`; for `ddp`, `world_size` = `resources.gpu_count`).
- **Depends on:** Abdullah (runtime by Wed 18); Hamda + Fatma (2-GPU machine); Maitha (multi-GPU placement by Sat 21).
- **Who depends on them:** Hilal + Adel (benchmark results by Tue 24, for the comparison page).

| Dates | Task | Waiting on |
|---|---|---|
| Thu 12 – Fri 13 | Install the tools and PyTorch. Run a tiny two-process DDP test on CPU to learn the setup. | — |
| Sat 14 – Sun 15 | Write the benchmark plan and scripts: time, speed-up, efficiency, GPU-hours, cost. | — |
| Mon 16 – Wed 18 | Plug DDP into Abdullah's training code and test it locally. | Abdullah (4): runtime by Wed 18 |
| Thu 19 – Fri 20 | Write the parallelism selector rules (single, DDP or parallel trials). Checkpoint 2. | — |
| Sat 21 – Tue 24 | Real 2-GPU run in the cloud. Benchmark 1 GPU vs 2 GPUs. Tune data-loader workers. Results to Hilal and Adel by Tue 24. Checkpoint 3. | Hamda + Fatma (6): 2-GPU machine · Maitha (7): multi-GPU placement by Sat 21 |
| Wed 25 – Fri 27 | Feature freeze. Write docs/BENCHMARKS.md. Numbers for the demo. Rehearsal Thu 26. | — |

### Student 6 — Hamda + Fatma (partners) — Terraform and cloud infrastructure
- **Role:** build every cloud resource with code (Terraform), so the whole platform runs on AWS and can be destroyed and rebuilt safely.
- **Folder:** `infrastructure/` (no port); also `docs/DEPLOYMENT_GUIDE.md` and `contracts/pricing.yaml`. Partners review each other.
- **Responsibilities:** network design; Terraform modules (network, storage, database, queues, compute); container registry and deployment infrastructure; CPU/GPU training resources; remote state (S3 backend with locking, restricted access); dev and staging configuration; deploy and clean-up docs; tagging (`Project`, `Environment`, `Owner`) and cost visibility; real prices in `pricing.yaml`.
- **Deliverables:** Terraform repo, networking, database and storage, compute, deployment scripts, infrastructure docs.
- **Acceptance test:** the group creates the dev environment with Terraform, deploys CloudTrain, changes infrastructure through Terraform, and safely destroys disposable resources.
- **Mandatory Terraform demos:** apply creates dev · inspect the plan · deploy the services · change a parameter (e.g. worker capacity) · apply it without manual rebuilding · show state and dependencies · destroy disposable resources safely.
- **Endpoints / queues:** none; you CREATE the queues (`training-jobs` with dead-letter redrive to `training-jobs-dlq`, `job-events`, all encrypted) and buckets (`datasets`, `artifacts`). **Contracts:** `pricing.yaml`, the cloud mapping (PART 5 §13).
- **Depends on:** the instructors (AWS account, GPU quota — request it Thu 12, approval can take days).
- **Who depends on them:** everyone (services on AWS by Sun 22); Faisal, Mariam, Maitha, Salem (buckets, database, queues, image registry by Wed 18); Abdullah and Maitha (first GPU machine by Thu 19); Ahmed + Abdulla (2-GPU machine); Majed (ECS by Sun 22).

| Dates | Task | Waiting on |
|---|---|---|
| Thu 12 Nov | Confirm the AWS account with the instructors. Request GPU quota today: approval can take days. | Instructors: AWS account |
| Fri 13 – Sun 15 | Remote state in S3 with locking. Folder layout from the brief. Network module. Checkpoint 1. | — |
| Mon 16 – Wed 18 | Dev environment: S3 buckets, database, queues, image registry. Show plan and apply. Ready for Faisal, Mariam, Maitha and Salem by Wed 18. | — |
| Thu 19 – Fri 20 | GPU machine for Abdullah and Maitha by Thu 19. Permissions with Salem. Prices in pricing.yaml. Checkpoint 2. | AWS: GPU quota approved |
| Sat 21 – Tue 24 | Services on ECS Fargate by Sun 22. 2-GPU machine for Ahmed and Abdulla. Change worker capacity through Terraform. Monitoring resources. Checkpoint 3. | — |
| Wed 25 – Fri 27 | Feature freeze. Deployment guide. Rehearse destroy on a copy. Run terraform destroy after we submit. | — |

### Student 7 — Maitha — Cloud resource scheduling and compute
- **Role:** decides where and when each training job runs, starts the machines, and frees them afterwards.
- **Folder / port:** `scheduler/` (8004, internal only). No partner.
- **Responsibilities:** the scheduler (the ONLY reader of `training-jobs`); CPU vs GPU choice per job; starting workers on Hamda and Fatma's infrastructure; placement and capacity; quotas and concurrency limits; queueing when capacity is full; releasing machines after each job; worker health monitoring and recovery. PostgreSQL schema `scheduler` (workers, capacity, quotas).
- **Deliverables:** compute scheduler, resource allocation, worker lifecycle manager, scheduling policies, integration with the cloud training infrastructure.
- **Acceptance test:** CPU and GPU jobs land on the right machines, jobs wait when capacity is full, and machines are released after use.
- **Endpoints:** `GET /health`, `GET /metrics` only. **Calls:** `POST training-worker:8010/internal/run` (local) or start an EC2 instance with the job form (cloud); `POST job-service:8003/internal/jobs/{id}/status` (SCHEDULED, RUNNING, with machine type and times; a 409 answer means the job was cancelled → stop the worker, release the machine).
- **Queues:** READS `training-jobs` (only you). Delete the message once a worker has accepted the job; after that the job is protected by the heartbeat lease. **Contracts:** `scheduler.yaml`, `training-job.schema.json`, `job-states.md`.
- **Depends on:** Mariam (jobs in the queue by Wed 18); Hamda + Fatma (GPU machine by Thu 19); Abdullah (the worker).
- **Who depends on Maitha:** Ahmed + Abdulla (multi-GPU placement by Sat 21); Mariam (status updates).

| Dates | Task | Waiting on |
|---|---|---|
| Thu 12 – Fri 13 | Install the tools, send Ali your GitHub username, read this plan and the architecture doc. | — |
| Sat 14 – Sun 15 | Replace the stand-in with your own service. Read from the local queue. | Ali (1): repo ready Fri 13 |
| Mon 16 – Wed 18 | Read jobs from the queue (you are the only reader), hand each to the local worker, report Scheduled and Running to Mariam. | Mariam (3): jobs in the queue by Wed 18 |
| Thu 19 – Fri 20 | Choose CPU or GPU per job. Start a cloud worker. Release the machine after. Checkpoint 2. | Hamda + Fatma (6): GPU machine by Thu 19 |
| Sat 21 – Tue 24 | Multi-GPU placement for Ahmed and Abdulla by Sat 21. Capacity limits, waiting when full, heartbeat watch and recovery with Mariam. Checkpoint 3. | — |
| Wed 25 – Fri 27 | Feature freeze. Tests and docs. Rehearse the failure demo Thu 26. | — |

### Student 8 — Majed — Model registry, deployment and inference
- **Role:** keeps every trained model version, puts the best one live, and answers predictions from it.
- **Folders / ports:** `model-registry/` (8006), `inference-service/` (8007), both internal. No partner.
- **Responsibilities:** model registration and versioning (MLflow Model Registry); linking models to runs and datasets; promotion workflow; inference containers; cloud prediction API; health checks and deployment validation; rollback. PostgreSQL schema `registry`.
- **Deliverables:** registry integration, deployment API, inference service, version management, rollback.
- **Acceptance test:** a trained model is registered, deployed and queried through REST. A failed new deployment never replaces the healthy one.
- **Endpoints (public):** registry `POST /models` (from an MLflow run ID, linked to job and dataset version), `GET /models`, `GET /models/{id}/versions`, `GET /models/{id}/production`, `POST /models/{id}/versions/{v}/promote`, `POST /models/{id}/rollback`; inference `POST /predict` (image → prediction), `GET /model-info`, `GET /health`. **Internal:** Inference calls `GET model-registry:8006/models/{id}/production`; the registry calls MLflow on `mlflow:5000`. Note: `/model-info` is not routed through the gateway (only `/api/v1/predict/*` is).
- **Queues:** none. **Contracts:** `model-registry.yaml`, `inference-service.yaml`.
- **Depends on:** Abdullah (real model by Fri 20); Hamda + Fatma (ECS by Sun 22); Salem (deploy pipeline).
- **Who depends on Majed:** Hilal + Adel (prediction API on AWS by Tue 24).

| Dates | Task | Waiting on |
|---|---|---|
| Thu 12 – Fri 13 | Install the tools, send Ali your GitHub username, read this plan and the architecture doc. | — |
| Sat 14 – Sun 15 | Replace both stand-ins with your own services. /health works. | Ali (1): repo ready Fri 13 |
| Mon 16 – Wed 18 | Register a model from an MLflow run (use a small test run until Abdullah's real model arrives). | — |
| Thu 19 – Fri 20 | Promote a version. Inference loads the live version and answers /predict. Checkpoint 2. | Abdullah (4): real model by Fri 20 |
| Sat 21 – Tue 24 | New version must pass /health before taking traffic. Rollback. Running on AWS. Prediction API to Hilal and Adel by Tue 24. Checkpoint 3. | Hamda + Fatma (6): ECS by Sun 22 · Salem (9): deploy pipeline |
| Wed 25 – Fri 27 | Feature freeze. Tests and docs. Rehearsal Thu 26. | — |

### Student 9 — Salem — CI/CD, security and DevSecOps
- **Role:** makes every change tested, built, scanned and deployed automatically, and makes the platform secure (login, secrets, permissions).
- **Folders:** `.github/workflows/` (changes need Ali's approval), `security/`. No port. No partner.
- **Responsibilities:** GitHub Actions; lint, tests and image builds; image scanning and dependency checks; login and permissions (default Cognito, or another OIDC provider); secrets (AWS Secrets Manager) and least-privilege IAM; environment deployment rules; approval and rollback procedures; security testing across services.
- **Deliverables:** CI/CD pipelines, identity integration, security policies, secret management, image scanning, deployment automation, security tests.
- **Acceptance test:** a code change triggers tests and builds, deploys to staging, is promoted through approval, and unauthorised access is rejected.
- **Endpoints:** none of your own. Real login plugs into the gateway's one login function (`gateway/app/auth.py`, `AUTH_MODE=jwt` with `JWT_JWKS_URL`, `JWT_ISSUER`, `JWT_AUDIENCE`). The starter CI (`ci.yml`) is Ali's; you extend it. **Queues:** none. **Contracts:** `error-format.json` (401/403), login rules in PART 5 §6.
- **Depends on:** Ali (API contracts, repo); Hamda + Fatma (image registry by Wed 18).
- **Who depends on Salem:** Ali (real login in the gateway by Fri 20); Majed (deploy pipeline); everyone (CI).

| Dates | Task | Waiting on |
|---|---|---|
| Thu 12 – Fri 13 | Review Ali's starter CI and branch rules. Plan secrets and login. | Ali (1): repo ready Fri 13 |
| Sat 14 – Sun 15 | CI for every service: lint, tests, builds. Checkpoint 1. | — |
| Mon 16 – Wed 18 | Push images to ECR. Dependency checks. Set up the login provider (Cognito or another). | Hamda + Fatma (6): image registry by Wed 18 |
| Thu 19 – Fri 20 | Real login inside the front door, with Ali, by Fri 20. Image scanning. Checkpoint 2. | — |
| Sat 21 – Tue 24 | Deploy to staging, approval to promote, rollback, least-privilege permissions, security tests. Checkpoint 3. | — |
| Wed 25 – Fri 27 | Feature freeze. Docs. Show the pipeline at the rehearsal Thu 26. | — |

### Student 10 — Hilal + Adel (partners) — Web portal, observability and evaluation
- **Role:** the website users actually see, the monitoring dashboards, and the final performance and cost evaluation.
- **Folder / port:** `portal/` (3000, published); also `docs/EVALUATION.md`. Partners review each other. Default framework Next.js on Node 24 (the brief allows React or Next.js).
- **Responsibilities:** the portal; integrating the project, dataset, job and model APIs; job monitoring and experiment comparison pages; job alerts (the portal IS the notification service); compute usage and cost; CloudWatch / Prometheus / Grafana; end-to-end UI tests; the performance and reliability evaluation; the final demo dashboard.
- **Deliverables:** portal, training dashboard, comparison views, monitoring integration, end-to-end tests, evaluation report.
- **Acceptance test:** a user completes the whole flow, from upload to deployed inference, through the web interface with real metrics and status.
- **Endpoints:** serves web pages only, plus `/health` and `/metrics`. **The portal calls ONLY the gateway** (`NEXT_PUBLIC_GATEWAY_URL`, port 5810). Alerts: `GET /api/v1/jobs/events?after=<last event_id>` every 5–10 seconds with back-off. MLflow results: `GET /api/v1/experiments/...` (read only).
- **Queues:** monitoring READS `job-events` (the only reader). **Contracts:** all public APIs; `events/job-event.schema.json`.
- **Depends on:** everyone's APIs: Faisal and Mariam (first real versions); Mariam (alert feed by Fri 20); Ahmed + Abdulla (benchmark results by Tue 24); Majed (prediction API by Tue 24).
- **Who depends on them:** everyone, for the final demo; Ali (evaluation for the final report).

| Dates | Task | Waiting on |
|---|---|---|
| Thu 12 – Fri 13 | Install the tools. Choose React or Next.js. Sketch the pages. | — |
| Sat 14 – Sun 15 | Replace the portal stand-in. Health and projects page through the front door. | Ali (1): repo ready Fri 13 |
| Mon 16 – Wed 18 | Dataset upload page and submit-job page. | Faisal (2) and Mariam (3): first real versions |
| Thu 19 – Fri 20 | Job page with live status and alerts. MLflow results. Checkpoint 2. | Mariam (3): alert feed by Fri 20 |
| Sat 21 – Tue 24 | Comparison page (1 GPU vs 2 GPUs), models and prediction page, cost page, dashboards. Checkpoint 3. | Ahmed + Abdulla (5): results · Majed (8): prediction API, both by Tue 24 |
| Wed 25 – Fri 27 | Feature freeze. End-to-end website test. Evaluation report. Demo dashboard for the rehearsal Thu 26. | — |

### Definition of done (every task)
- The work matches the contract in `contracts/` (or an approved Contract change issue).
- `/health` and `/metrics` work; every error uses the shared error format; logs are JSON with `request_id`.
- Tests added for the main path and at least one failure path; `make check` passes.
- No secrets, keys, `.env` or Terraform state committed; configuration only from environment variables.
- README updated. Merged through a pull request that says `Closes #N`, reviewed by a teammate (and Ali for shared files).
- For your final task: your acceptance test passes in the integrated system, and your walk-through step (PART 4) is switched on in `tests/integration/test_walkthrough.py`.

### How everyone is assessed (individual, from the brief)

| Criterion | Weight |
|---|---|
| Own subsystem implementation | 30% |
| Integration with others' services | 25% |
| Cloud deployment and technical correctness | 15% |
| Testing, reliability and security | 15% |
| Technical documentation and explanation | 10% |
| Final demonstration | 5% |

Everyone must understand the overall architecture; each person is assessed mainly on their own subsystem and its integration.

---

## PART 2 — How we work

**Tools to install:** Docker Desktop, git, GitHub CLI (`gh`), Python 3.11, Node 24, make.
On a Mac: `brew install --cask docker-desktop`, `brew install gh`, Python 3.11 via `uv python install 3.11`
(or python.org), Node 24 from nodejs.org. Then `gh auth login`.

**Start the whole system on your laptop:**
```bash
git clone https://github.com/ali-ahmed-alshehhi/cloudtrain.git
cd cloudtrain
make up          # starts all 12 containers and waits until every one is healthy (first time: a few minutes)
```
Then open http://localhost:3000 (portal) and http://localhost:5810/health (gateway). `make down` stops it,
`make reset` wipes all data, `make logs` shows the logs, `make help` lists everything.
Local login for testing: `Authorization: Bearer <DEV_AUTH_TOKEN from .env>` (until Salem's real login).

**The seven steps for every change:**
1. Pick your issue on the board (https://github.com/users/ali-ahmed-alshehhi/projects/1) and move it to **In progress**.
2. Create a branch named `<name>/<short-task>`: `git switch main && git pull && git switch -c faisal/upload-checksums`.
3. Commit small changes with clear messages.
4. Run `make check` (lint + unit tests + start everything + contract tests + walk-through). It must be green.
5. Open a pull request with `Closes #N`: `git push -u origin <branch>` then `gh pr create --fill`. Move the card to **In review**.
6. CI runs; a teammate is asked to review automatically (your partner for pair folders; the teammate who integrates with you otherwise). **Ali must also approve any change to shared files** (`contracts/`, `gateway/`, `docker-compose.yml`, `Makefile`, `local/`, `tests/`, `docs/ARCHITECTURE.md`, `team.yml`, `.github/`).
7. Merge: the issue closes itself and moves to **Done**.

`main` is protected: no direct pushes, 1 approval, CI must pass, branch up to date. Your issues carry your
label (e.g. `s2-faisal`), a phase label, a milestone (Checkpoint 1/2/3, Ready) and a due date.
Blocked? Add the `blocked` label and say who you are waiting for; keep working with the stand-in.
Full details: `docs/TEAM_WORKFLOW.md`.

**Get notified:** install the GitHub mobile app; on the repo page click **Watch → Custom → Issues and Pull
requests → Apply**. Accept the collaborator invitation e-mail from GitHub (send Ali your GitHub username first).

**Meetings:** a 15-minute online check-in every day (done / next / blocked); checkpoint calls on
**Sun 15, Fri 20 and Tue 24 Nov**, where each person shows their part working with at least one other part.

---

## PART 3 — What you can change freely vs what needs agreement

**Free (inside your own folder):** code structure, libraries, internal tables, extra endpoints, tests, and
your listed defaults — portal framework (Hilal + Adel), login provider (Salem), plain EC2 vs AWS Batch
(Maitha + Hamda + Fatma). Record a changed default in `docs/decisions/`.

**Needs agreement:** anything in `contracts/` (public endpoints, the training job form, events, the error
format, pricing), ports, gateway routes, queue readers, shared rules, `docker-compose.yml`.
Process: open a **Contract change** issue → tag Ali and the affected owners → agree → update `contracts/`
**first** (its own pull request) → then the code → record it in `docs/decisions/`.

If you think the plan is wrong, say so. The plan can change with a reason, as the instructors allow.

---

## PART 4 — All the routes to finish the project

**The key question the project must answer:** *How do we turn an ML training script into a scalable,
automated, reliable and reusable cloud ML service?* The team must explain why a pile of separate Python
scripts is not enough for a production ML platform, and how microservices, cloud infrastructure,
distributed computing and DevOps solve that.

**End-to-end walk-through (final demo and main integration test, `tests/integration/test_walkthrough.py`):**

| # | Step | Owner | Status today |
|---|---|---|---|
| 1 | Log in | Salem | skipped until Fri 20 |
| 2 | Create project "Image Classification": `POST /api/v1/projects` → 201 `project-01` | Ali | runs |
| 3 | Upload CIFAR-10: `POST /api/v1/datasets` → 201 `dataset-07` v1 | Faisal | runs (stand-in) |
| 4 | Submit job (ResNet-18, settings, resources, strategy): `POST /api/v1/jobs` → 202 `job-104` | Mariam | runs (stand-in) |
| 5 | Queued, then Scheduled on the right machine, then Running | Maitha | runs (stand-in) |
| 6 | Training with live metrics in MLflow and the model saved to S3 | Abdullah; Ahmed + Abdulla | skipped until Fri 20 |
| 7 | Job Succeeded, alert shown in the portal, machine released | Mariam, Maitha, Hilal + Adel | runs (stand-in); machine release skipped |
| 8 | Compare a single-GPU run with a DDP run | Hilal + Adel; Ahmed + Abdulla | skipped until Tue 24 |
| 9 | Register the best model: `POST /api/v1/models` → 201 v1 | Majed | skipped until Fri 20 |
| 10 | Promote v1; inference passes `/health` before taking traffic | Majed | skipped until Tue 24 |
| 11 | Send an image: `POST /api/v1/predict` → 200 prediction | Majed | skipped until Fri 20 |
| 12 | View compute usage, GPU-hours and estimated cost | Hilal + Adel | skipped until Tue 24 |

The final demo must also show the Terraform-provisioned infrastructure, the CI/CD pipeline, and **one
failure-recovery scenario**: a worker is killed mid-job, the heartbeat stops, the job is retried and
finishes (`tests/integration/test_failure_recovery.py`, switched on when Mariam and Maitha deliver).

**Schedule (ready Fri 27 Nov 2026):**

| Dates | Phase | Must work by the end |
|---|---|---|
| Thu 12 – Sun 15 Nov | Foundation | Repo, contracts and stand-ins live; AWS account confirmed and GPU quota requested Thu 12; Terraform remote state; starter CI; every owner's own service answers `/health`. **Checkpoint 1: Sun 15.** |
| Mon 16 – Fri 20 Nov | Core | Project → dataset → job through the gateway; Terraform dev environment up; first real cloud training run on 1 GPU; MLflow; scheduler placing jobs; model registered; real login. **Checkpoint 2: Fri 20.** |
| Sat 21 – Tue 24 Nov | Integration | Services on AWS; 2-GPU DDP run and benchmark; inference with rollback; retries, cancel and dead-worker recovery; full flow in the portal; dashboards and cost. **Checkpoint 3: Tue 24.** |
| Wed 25 – Fri 27 Nov | Finish | Feature freeze Wed 25; full rehearsal Thu 26; tests, docs, benchmarks, evaluation and final report; **ready and submitted Fri 27.** |
| Sat 28 Nov | Safety day | Fixes only. `terraform destroy` after submission. |

Scope: build the brief's **minimum** in every area first; advanced items only if everything else is done.

**Hand-offs** (if one is late, the receiver keeps working with the stand-in and the giver tells the group the same day; each is also an issue on the board):

| Date | From | To | What |
|---|---|---|---|
| Thu 12 | Everyone | Ali | GitHub usernames |
| Thu 12 | Instructors | Hamda + Fatma | AWS account (GPU quota requested today) |
| Fri 13 | Ali | Everyone | Repo, contracts, stand-ins, tasks, this map |
| Tue 17 | Faisal | Mariam | Dataset version check |
| Wed 18 | Hamda + Fatma | Faisal, Mariam, Maitha, Salem | Buckets, database, queues, image registry |
| Wed 18 | Faisal | Abdullah | Download link for training data |
| Wed 18 | Mariam | Maitha | Jobs in the queue |
| Wed 18 | Abdullah | Ahmed + Abdulla | Training runtime for DDP |
| Thu 19 | Hamda + Fatma | Abdullah, Maitha | First GPU machine |
| Fri 20 | Abdullah | Majed | First real trained model |
| Fri 20 | Mariam | Hilal + Adel | Alert feed |
| Fri 20 | Salem | Ali | Real login in the front door |
| Sat 21 | Maitha | Ahmed + Abdulla | Multi-GPU placement |
| Sun 22 | Hamda + Fatma | Everyone | Services running on AWS |
| Tue 24 | Ahmed + Abdulla | Hilal + Adel | Benchmark results |
| Tue 24 | Majed | Hilal + Adel | Prediction API on AWS |

**Minimum vs advanced:**

| Area | Minimum | Advanced |
|---|---|---|
| Microservices | 6+ integrated services | Service mesh, distributed tracing |
| Cloud | Real deployment with Terraform | Multi-environment, multi-region |
| Training | Single-worker and DDP | Tensor / pipeline parallelism |
| Scheduling | Queue and resource allocation | Priority / fair-share |
| Data | Object storage and versioning | Lineage and validation pipelines |
| MLOps | MLflow and model registry | Automated retraining |
| Deployment | Containerised inference API | Canary or blue-green |
| CI/CD | Automated build, test, deploy | GitOps and policy gates |
| Monitoring | Metrics, logs, dashboard | SLO alerting, anomaly detection |
| Cost | GPU-hour reporting | Budget-aware scheduling |

**Final deliverables:** the Git repo (microservices, frontend, training code, Terraform modules, CI/CD
workflows); `docs/ARCHITECTURE.md` (architecture + deployment diagrams); `docs/api/` (OpenAPI);
`docs/database/` (one page per schema); `docs/DEPLOYMENT_GUIDE.md`; `docs/TESTING.md`;
`docs/BENCHMARKS.md` (Ahmed + Abdulla); `docs/EVALUATION.md` (Hilal + Adel); `docs/decisions/` (one short
file per important decision); `docs/FINAL_REPORT.md` (engineering decisions, trade-offs, limitations,
lessons learned, the answer to the key question); a live demo of the integrated platform.

**Open decisions** (`docs/OPEN_DECISIONS.md`):
1. Whose AWS account and budget, and is GPU quota approved for at least 2 GPUs? (instructors)
2. Which tabular dataset is the second use case? (Abdullah)
3. Cognito or another OIDC provider? (Salem)
4. Workers on plain EC2 or AWS Batch? (Maitha + Hamda + Fatma)
5. React or Next.js for the portal? (Hilal + Adel)
6. Time of the daily online check-in and the checkpoint calls on Sun 15, Fri 20 and Tue 24. (Ali, with the team)
7. Repository visibility: public since 12 Nov; the instructors to confirm.

---

## PART 5 — The full architecture (source: `docs/ARCHITECTURE.md`; exact shapes: `contracts/`)

### 1. What CloudTrain is
A simplified Amazon SageMaker / Google Vertex AI / Azure ML, built mainly with open-source tools on AWS.
A user logs in and creates a project, uploads and versions a dataset, configures a training job (model,
hyperparameters, CPU/GPU, parallelism) and submits it; the job trains on cloud CPU/GPU (single GPU or
distributed); results are tracked in MLflow; single-GPU and distributed runs can be compared; the best model
is registered and deployed behind a REST API; the user sends an image and gets a prediction; compute usage
and estimated cost are visible. Everything happens through one web portal and one gateway. A collection of
disconnected demos does not pass.

Learning outcomes to demonstrate: architecture and decomposition into microservices; REST API design and
service communication; database design, persistent storage and asynchronous messaging; Docker; Terraform;
cloud provisioning, networking, security and storage; distributed ML training and parallelism; CI/CD with
automated testing and deployment; model versioning, experiment tracking and inference serving;
observability, failure recovery, scalability and cost management. The strongest projects make sound
choices, integrate reliably, justify trade-offs with measurements, and deliver a working system.

### 2. Main principles
1. **Microservices:** each service owns one capability, its own folder, database schema and Docker image, deployable alone; workloads scale separately (upload = storage, training = heavy and long, inference = fast).
2. **One front door:** all API traffic enters through the gateway (5810). The portal (3000) is the only other published port and only serves pages; it calls only the gateway. Services never read another service's database; they call its API.
3. **Asynchronous long work:** `POST /jobs` returns 202 with a job ID at once; the job goes on a queue. Nobody keeps a request open while training runs.
4. **Events, not polling:** status changes are published as events; where a client must poll, it waits at least 5 seconds and backs off.
5. **Idempotent:** a queue message can arrive twice and must not do the work twice; create requests accept an `Idempotency-Key`.
6. **Persistent state:** datasets, models, experiment metadata and job records survive container restarts (in the cloud; locally LocalStack loses files on restart — see §11).
7. **Cloud-native, infrastructure as code:** services and training run in AWS; Terraform creates all cloud resources, with remote state, locking and restricted access; nothing by hand.
8. **Observable:** JSON logs with `request_id`; `/health` and `/metrics` (Prometheus) everywhere.
9. **Automated:** every change goes through a pull request, CI checks and a review before `main`.

### 3. Services, owners, ports

| Service | Folder | Owner(s) | Port | Reached by |
|---|---|---|---|---|
| API Gateway | `gateway/` | Ali | **5810 (published)** | browser / portal |
| Projects (identity and projects) | `project-service/` | Ali | 8001 | gateway, other services (membership) |
| Datasets | `dataset-service/` | Faisal | 8002 | gateway, job service, workers |
| Training Jobs | `job-service/` | Mariam | 8003 | gateway, scheduler, workers |
| Scheduler | `scheduler/` | Maitha | 8004 | internal only |
| Training worker | `training/` | Abdullah | 8010 (local dev only) | scheduler |
| Distributed training (DDP) | `training/distributed/` | Ahmed + Abdulla | — (in the worker) | — |
| MLflow (tracking + registry backend) | `mlflow/` (official image + drivers) | Abdullah | 5000 | gateway (read only), workers, registry |
| Model Registry | `model-registry/` | Majed | 8006 | gateway, inference |
| Inference | `inference-service/` | Majed | 8007 | gateway |
| Web Portal | `portal/` | Hilal + Adel | **3000 (published)** | browser |
| Terraform | `infrastructure/` | Hamda + Fatma | — | — |
| CI/CD, login, security | `.github/workflows/`, `security/` | Salem | — | — |
| Local infrastructure | PostgreSQL 5432, LocalStack 4566 (S3 + SQS) | Ali (compose) | not published | services |

The brief's 8 logical services: Identity & Project → Projects + login at the gateway; Dataset → Datasets;
Training Job → Training Jobs; Training Scheduler → Scheduler; Experiment Tracking → MLflow behind a gateway
adapter; Model Registry → Model Registry; Inference → Inference; Notification → job events shown in the
portal's alert feed and the monitoring stack (no separate container; alerts in the portal only, not by
e-mail; a `job-events` consumer can be added later — `docs/decisions/0002`).

### 4. Gateway routes (`gateway/app/routes.yaml`)

| Public path | Forwards to | Methods |
|---|---|---|
| `/api/v1/users/me`, `/api/v1/projects/*` | `project-service:8001` (strip `/api/v1`) | all |
| `/api/v1/datasets/*` | `dataset-service:8002` (strip `/api/v1`) | all |
| `/api/v1/jobs/*` | `job-service:8003` (strip `/api/v1`) | all |
| `/api/v1/experiments/*` | `mlflow:5000/api/2.0/mlflow/*` (rewrite) | GET, plus POST on paths ending in `/search` only (read-only adapter) |
| `/api/v1/models/*` | `model-registry:8006` (strip `/api/v1`) | all |
| `/api/v1/predict/*` | `inference-service:8007` (strip `/api/v1`) | all |
| `/health`, `/metrics` | the gateway itself | GET |

On every request the gateway verifies the login token (JWT), sets `X-User-Id` (from the token — a
caller's own `X-User-Id` is replaced) and `X-Request-Id` (kept or created), and forwards with a 10-second
timeout (uploads 300 s). A service that is down or slow → **503**; any path containing `/internal/` → **404**;
a method not allowed → **405** with an `Allow` header. CORS allows `http://localhost:3000` and `DEPLOYED_PORTAL_URL`.
MLflow's own errors are translated into the shared error format.

### 5. Public API per service (owners may add endpoints, never break these)
- **Projects:** `POST /projects`, `GET /projects`, `GET /projects/{id}`, `POST /projects/{id}/members`, `GET /users/me`
- **Datasets:** `POST /datasets`, `GET /datasets?project_id=`, `GET /datasets/{id}`, `POST /datasets/{id}/versions`, `GET /datasets/{id}/versions/{v}`, `GET /datasets/{id}/versions/{v}/download`
- **Training Jobs:** `POST /jobs` → 202, `GET /jobs?project_id=`, `GET /jobs/{id}`, `POST /jobs/{id}/cancel`, `GET /jobs/{id}/events`, `GET /jobs/events?after=&project_id=`
- **Model Registry:** `POST /models`, `GET /models`, `GET /models/{id}/versions`, `GET /models/{id}/production`, `POST /models/{id}/versions/{v}/promote`, `POST /models/{id}/rollback`
- **Inference:** `POST /predict`, `GET /model-info`, `GET /health`

**Internal calls (never through the gateway):** Training Jobs → `GET dataset-service:8002/datasets/{id}/versions/{v}`
(version exists?) · worker → `GET dataset-service:8002/internal/datasets/{id}/versions/{v}/download-url` ·
Scheduler → `POST job-service:8003/internal/jobs/{id}/status` · Scheduler → `POST training-worker:8010/internal/run`
(local) or start an EC2 instance (cloud) · worker → `POST job-service:8003/internal/jobs/{id}/heartbeat`
every `HEARTBEAT_INTERVAL_SECONDS` · worker → `POST job-service:8003/internal/jobs/{id}/status` · worker and
Model Registry → MLflow on `mlflow:5000` · Inference → `GET model-registry:8006/models/{id}/production` ·
any service → `GET project-service:8001/projects/{id}` with the user's `X-User-Id` (membership: 200/403/404).

### 6. Shared rules (every service)
1. FastAPI, OpenAPI at `/openapi.json`, behaving as its file in `contracts/openapi/` (checked by `make contract`).
2. **Error format** for every non-2xx answer: `{"error": {"code": "DATASET_NOT_FOUND", "message": "Dataset dataset-07 does not exist", "request_id": "req-8f2a"}}`; codes `UPPER_SNAKE_CASE`.
3. **Status codes:** 200 read · 201 created · 202 accepted for long work · 400 bad input · 401 not logged in · 403 not allowed · 404 not found · 405 method not allowed · 409 conflict/duplicate · 422 validation · 429 slow down · 503 dependency down.
4. **Login:** the gateway verifies the JWT; local dev mode (`AUTH_MODE=dev`, only allowed when `ENVIRONMENT=local`) accepts the fixed test token from `.env`; Salem's real login goes behind the same function. Services trust only gateway headers and check membership through the Projects service.
5. **Idempotency:** `Idempotency-Key` on create requests returns the first result; queue consumers store the `event_id`s they handled.
6. `GET /health` 200 when ready; `GET /metrics` Prometheus format.
7. **Logs:** one JSON line per request with `timestamp`, `service`, `level`, `request_id`, `path`, `status`, `duration_ms`.
8. **Naming:** plural nouns in paths, `snake_case` JSON, IDs `<kind>-<n>` (`job-104`), ISO 8601 UTC dates, public paths start with `/api/v1/`.
9. **Configuration:** only environment variables, nothing hard-coded, every variable in `.env.example`.

### 7. Who reads which queue (one reader per queue)

| Queue | Written by | Read by |
|---|---|---|
| `training-jobs` | Training Jobs | **Scheduler only.** Workers never read it; the scheduler hands each job to one worker. |
| `training-jobs-dlq` | SQS (after the retry limit) | Training Jobs, for failure reports |
| `job-events` | Training Jobs, on every status change | Monitoring (Hilal + Adel). Training Jobs also stores every event to serve the alert feed. |

Queue settings: encryption on; dead-letter redrive on `training-jobs`; the visibility timeout covers
scheduling time; the scheduler deletes the message once a worker accepted the job — after that the job is
protected by the heartbeat lease, not the queue.

### 8. The training job form (`contracts/training-job.schema.json`)
```json
{"job_id": "job-104", "project_id": "project-01", "dataset_id": "dataset-07", "dataset_version": 2,
 "model": "resnet18", "hyperparameters": {"epochs": 10, "batch_size": 32, "learning_rate": 0.001},
 "resources": {"gpu_count": 2, "cpu_cores": 8, "memory_gb": 32},
 "parallelism": {"strategy": "ddp", "world_size": 2},
 "execution": {"max_runtime_minutes": 120, "retry_limit": 2}}
```
`strategy`: `single` (world_size 1) or `ddp` (world_size ≥ 2 and = `gpu_count`); later `hparam_search`
(recommended), `tensor` / `pipeline` (advanced, real multi-GPU hardware only). `dataset_version` is our
addition so a job always trains on a fixed version. `POST /jobs` takes the form without `job_id`. Validated by
Training Jobs, read by the Scheduler, run by the worker. Changing it needs Mariam, Maitha, Abdullah,
Ahmed/Abdulla and Ali to agree.

### 9. Job status steps (`contracts/job-states.md`) and events
- `QUEUED → SCHEDULED → RUNNING → SUCCEEDED`; `QUEUED / SCHEDULED / RUNNING → CANCELLED` (the user cancels; the scheduler stops the worker and releases the machine).
- `RUNNING → FAILED` when training errors, `max_runtime_minutes` passes, or no heartbeat for `HEARTBEAT_TIMEOUT_SECONDS` (default 120; interval default 30; settings, not contract rules; the timeout stays ≥ 3 × the interval).
- `FAILED → QUEUED` while `retry_limit` is not used up (event `job.retrying`); then it stays `FAILED` and a report goes to `training-jobs-dlq`.
- Every change is stored in the job's history and published to `job-events`. **A job can never stay RUNNING forever.** A report not allowed from the current status gets 409; that is how the scheduler and worker learn of a cancel (the heartbeat answer also carries the status).
- Events (`contracts/events/job-event.schema.json`): `event_id`, `event_type`, `job_id`, `project_id`, `occurred_at`, `data`; types `job.queued`, `job.scheduled`, `job.running`, `job.succeeded`, `job.failed`, `job.cancelled`, `job.retrying`.

### 10. Cost
`contracts/pricing.yaml` lists the hourly price per machine type (placeholders now; Hamda + Fatma fill in AWS
prices). The Scheduler reports machine type and start/end times; Training Jobs computes `gpu_hours`
(GPUs × hours) and `estimated_cost_usd`; the portal shows them per job and per project.

### 11. Data stores

| Store | Local stand-in | Cloud | Owner |
|---|---|---|---|
| PostgreSQL schema `projects` | `postgres` container | RDS PostgreSQL | Ali |
| schema `datasets` (records, versions, checksums, lineage, audit) | same | same | Faisal |
| schema `jobs` (jobs, history, events, retries, cost) | same | same | Mariam |
| schema `scheduler` (workers, capacity, quotas) | same | same | Maitha |
| schema `mlflow` (runs and model registry) | same | same | Abdullah |
| schema `registry` (deployments, live version, rollback history) | same | same | Majed |
| Bucket `datasets` (one folder per version) | LocalStack S3 | S3 | Faisal |
| Bucket `artifacts` (checkpoints, models) | LocalStack S3 | S3 | Abdullah, Majed |
| Queues `training-jobs`, `training-jobs-dlq`, `job-events` | LocalStack SQS | SQS | see §7 |

Each service has its own database user that can touch only its own schema (created by `local/postgres/init.sh`
locally, by the infrastructure setup in the cloud; service users cannot create schemas). Locally LocalStack
keeps files and queue messages in memory: they are lost when it restarts (MinIO, the plan's original choice,
no longer publishes Docker images — `docs/decisions/0005`). PostgreSQL data stays until `make reset`.

### 12. Training and parallelism

| Technique | Level | Example |
|---|---|---|
| Single-worker training | Mandatory | ResNet-18 on 1 GPU |
| Data parallelism | Mandatory | PyTorch DistributedDataParallel |
| CPU data-loading parallelism | Mandatory | Several DataLoader workers |
| Hyperparameter search parallelism | Recommended | Several independent trials |
| Model / tensor parallelism | Advanced | Split a model across GPUs |
| Pipeline parallelism | Advanced | Split layers across devices |

Minimum: a real comparison of 1 GPU vs multi-GPU DDP (speedup, efficiency, throughput, GPU-hours, cost).
Tensor and pipeline parallelism only on real hardware, never simulated and presented as real GPU scaling.
The parallelism selector prefers: a single worker when the model fits on one GPU and the data is small;
DDP when throughput is the limit and several GPUs are available; model parallelism when the model does not
fit on one GPU; parallel trials for independent experiments — weighing GPU availability, memory, model
size, dataset size, communication overhead and budget. Two use cases: CIFAR-10 + ResNet-18, and one tabular
classification dataset (open decision).

### 13. Cloud mapping

| Part | AWS |
|---|---|
| Services, gateway, portal | ECS Fargate (stateless services) |
| Images | ECR |
| Training workers | EC2 CPU / GPU instances or AWS Batch, started per job (GPU training never runs on Fargate) |
| Database | RDS PostgreSQL |
| Files | S3 |
| Queues | SQS |
| Login | Cognito or external OIDC |
| Secrets | Secrets Manager |
| Logs and metrics | CloudWatch (+ Prometheus/Grafana) |
| Network | VPC: gateway and portal behind a load balancer in public subnets, everything else in private subnets |

Every resource tagged `Project`, `Environment`, `Owner`. Terraform state in an S3 backend with locking and
restricted access; state and secrets never committed. GPU machines run only while a job runs. `terraform
destroy` disposable environments after each test session. Encryption and least-privilege IAM everywhere.
Terraform layout: `infrastructure/environments/{dev,staging}/`, `infrastructure/modules/{networking,
security, database, object-storage, message-queue, container-registry, application-services,
training-compute, monitoring, iam}/`, plus `backend.tf`, `providers.tf`, `variables.tf`, `outputs.tf`.

### 14. Dependencies (from the brief)

| Student | Depends on | Integrates with |
|---|---|---|
| 1 Ali | 9 (identity) | all |
| 2 Faisal | 6 (storage) | 1, 3, 4 |
| 3 Mariam | 6 (queue, database) | 1, 4, 7, 10 |
| 4 Abdullah | 2 (datasets) | 3, 5, 7, 8 |
| 5 Ahmed + Abdulla | 4 (training runtime) | 6, 7, 10 |
| 6 Hamda + Fatma | cloud account and quotas | all |
| 7 Maitha | 6 (compute) | 3, 4, 5 |
| 8 Majed | 4 (artifacts) | 1, 9, 10 |
| 9 Salem | 1 (API contracts) | all |
| 10 Hilal + Adel | APIs and metrics from everyone | all |

Students 3, 4, 5 and 7 share the training job form.

### 15. The repo at a glance
`contracts/` (the agreed rules) · one folder per service, each with `README.md`, `Dockerfile`, `app/`,
`tests/` · `docker-compose.yml` + `Makefile` (`make up / down / reset / logs / test / lint / contract / e2e /
check / help`) · `local/` (start-up scripts) · `tests/integration/` (walk-through, failure recovery) ·
`tests/contract/` (Schemathesis) · `infrastructure/` (Terraform skeleton) · `.github/` (CI, reviewer
assignment, CODEOWNERS, templates) · `scripts/` (task creation, branch protection) · `docs/` (architecture,
APIs, database pages, decisions, testing, deployment, benchmarks, evaluation, final report, team workflow).
Tools: Python 3.11, FastAPI, Pydantic v2, httpx, SQLAlchemy 2 + Alembic, pytest, ruff, Schemathesis,
Docker + Docker Compose, Next.js on Node 24, Terraform.
