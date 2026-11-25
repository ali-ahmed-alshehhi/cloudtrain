# Terraform cloud infrastructure — `infrastructure/`

| Owners (partners) | Port | Contracts |
|---|---|---|
| Hamda + Fatma (Student 6) | — | `contracts/pricing.yaml`, the cloud mapping in `docs/ARCHITECTURE.md` |

## What it must do
Create **every** cloud resource with Terraform (nothing by hand): network, storage, database, queues,
container registry, the services' deployment, CPU/GPU training machines, monitoring and IAM.
Remote state in S3 with locking and restricted access. Dev and staging environments. Tagging and cost
visibility. Deploy and clean-up docs in `docs/DEPLOYMENT_GUIDE.md`. Prices in `contracts/pricing.yaml`.

## Run it on the AWS Emulator (Student 6)

We have no AWS account: the official **AWS Emulator** stands in for it (decision
[0011](../docs/decisions/0011-aws-emulator-instead-of-aws-account.md), which replaces 0009).
The app's `make up` still uses LocalStack (decision [0005](../docs/decisions/0005-localstack-for-s3.md)).

```bash
cd infrastructure
./scripts/emulator-up.sh
source ./scripts/emulator-env.sh        # every new terminal needs this again
terraform init
terraform plan  -var-file=environments/dev/emulator.tfvars.example
terraform apply -var-file=environments/dev/emulator.tfvars.example
terraform output
terraform destroy -var-file=environments/dev/emulator.tfvars.example
./scripts/emulator-down.sh
```

Creates the same names teammates already use: `datasets`, `artifacts`, `training-jobs`,
`training-jobs-dlq`, `job-events`.

**Remote state with locking:** `bootstrap/` creates the state bucket once, then the root module
moves its state there. Steps in [bootstrap/README.md](bootstrap/README.md).

> LocalStack still works for Terraform: `docker compose -f docker-compose.localstack.yml up -d`, then
> `-var-file=environments/dev/localstack.tfvars.example`.

## Cloud mapping (real AWS)

| Part | AWS |
|---|---|
| Services, gateway, portal | ECS Fargate |
| Images | ECR |
| Training workers | EC2 CPU/GPU or AWS Batch (**not** Fargate for GPU) |
| Database | RDS PostgreSQL |
| Files | S3 `datasets`, `artifacts` |
| Queues | SQS `training-jobs` (+ DLQ), `job-events` |
| Login | Cognito |
| Secrets | Secrets Manager |
| Logs/metrics | CloudWatch |
| Network | VPC public (ALB/gateway/portal) + private (everything else) |

## Modules status

| Module | Status |
|---|---|
| `networking` | VPC, public/private subnets, IGW, optional NAT |
| `security` | ALB / services / workers / database security groups |
| `object-storage` | S3 `datasets` + `artifacts` |
| `message-queue` | SQS `training-jobs` + DLQ + `job-events` |
| `container-registry` | ECR repos per service |
| `bootstrap/` (own folder) | S3 state bucket: versioned, encrypted, private, TLS only; locking with `use_lockfile` |
| `database` | RDS PostgreSQL 17 (private, encrypted, SSL forced) + master secret in Secrets Manager |
| `identity` | Cognito user pool + portal client + role groups (decision 0006; module from Salem #121) |
| `iam` | worker role + instance profile: read datasets, read/write artifacts, send `job-events`; nothing else |
| `training-compute` | GPU worker pools: launch template + Auto Scaling group on EC2 (decision 0012), optional internal load balancer; `gpu-1` (1 GPU) and `gpu-4` (4 GPUs) |
| `service-roles` | one least-privilege task role per service: only the buckets and queues its code calls |
| `monitoring` | CloudWatch log group per ECS service (`/cloudtrain/<env>/<service>`) and alarms (dead letters, job events not read; 5xx once the ALB exists) |
| `pulumi/` (own folder) | Pulumi layer above Terraform: reads its outputs, creates the CloudWatch dashboard only (decision 0013) |
| `application-services` | ECS Fargate cluster `<env>-cloudtrain`, services, public ALB (gateway :5810, portal :3000); uses monitoring log groups when enabled |

### Wed 18 hand-off: the dev environment on the emulator (#34, #66)

`environments/dev/emulator.tfvars.example` turns on networking, the image registry and the
database, so one `terraform apply` builds the whole dev environment (45 resources on the
emulator). `terraform output` then gives each teammate what they need:

| Output | What it is | Who needs it |
|---|---|---|
| `datasets_bucket`, `artifacts_bucket` | S3 bucket names | Faisal (datasets); Abdullah, Majed (artifacts) |
| `training_jobs_queue_url`, `training_jobs_dlq_url`, `job_events_queue_url` | SQS queue URLs | Mariam (sends jobs, reads the DLQ); Maitha (only reader of `training-jobs`) |
| `ecr_repository_urls` | one image repository per service | Salem (CI pushes the images) |
| `db_endpoint`, `db_master_secret_arn` | Postgres address and the master user's secret | Faisal, Mariam, Majed (services with tables); Salem (deploy) |
| `jwt_issuer`, `jwt_audience`, `jwt_jwks_url` | Cognito settings for `AUTH_MODE=jwt` | Ali (gateway); Salem (login) |
| `vpc_id`, `private_subnet_ids`, `services_security_group_id` | the network services and workers run in (the security group is empty on the emulator, see below) | Hamda + Fatma (ECS, training machines); Maitha |

On the emulator these addresses point at the emulator, not at AWS, so services keep using
`make up` for their own work. The names match `.env.example`, so nothing changes in service code
if a real AWS account appears later.

### Thu 19 hand-off: the first GPU machine (#35, #70)

`enable_training_compute = true` (on in `emulator.tfvars.example`) adds one Auto Scaling group of
`g4dn.xlarge` machines (1 GPU each) and the IAM role they run as. Outputs for Abdullah and Maitha:
`gpu_worker_autoscaling_group`, `gpu_worker_launch_template_id`, `worker_instance_profile_name`.
On start a machine writes `JOB_EVENTS_QUEUE_URL`, `DATASETS_BUCKET` and `ARTIFACTS_BUCKET` to
`/etc/cloudtrain-worker.env`. It has no keys: its IAM role gives it S3 and `job-events` only.

**Demo 4, change worker capacity:** set `worker_desired_capacity = 2` (or `-var worker_desired_capacity=2`)
and run `terraform apply`. The group changes in place; nothing is rebuilt. `worker_max_size` (default 2)
caps the number of GPU machines.

The emulator does not run a real GPU, so this shows the infrastructure, not training speed. On real AWS
set `worker_ami_id` to the Deep Learning Base GPU AMI of the region (any `ami-...` works on the emulator).

### Multi-GPU pool and worker addresses (#36)

`enable_training_compute = true` now builds **two worker pools** with the same module:

| Pool | Machine | GPUs | Size variable | Max variable |
|---|---|---|---|---|
| `gpu-1` | `gpu_instance_type` (`g4dn.xlarge`) | 1 | `worker_desired_capacity` | `worker_max_size` (2) |
| `gpu-4` | `multi_gpu_instance_type` (`g4dn.12xlarge`) | 4 | `multi_gpu_desired_capacity` | `multi_gpu_max_size` (1) |

`contracts/pricing.yaml` has no 2-GPU machine, so Ahmed and Abdulla's 2-GPU runs use `gpu-4` (a job pays
for the whole machine). Demo 4 works for both pools: change the size variable and run `terraform apply`.

**Worker addresses for the Scheduler.** With `enable_worker_load_balancers = true` (on in
`emulator.tfvars.example`) each pool gets an internal network load balancer on port 8010 that
health-checks `/health`. New machines join it by themselves. The output `worker_urls` maps machine type
to address, for example `{"g4dn.xlarge": "http://dev-cloudtrain-gpu-1-….elb.amazonaws.com:8010"}`.
Maitha reads it as `TRAINING_WORKER_URLS` (JSON); `TRAINING_WORKER_URL` stays for `local-cpu`, so
`make up` doesn't change (#70). The workers' security group now only accepts port 8010: from the
services, and from inside the VPC for the load balancer's health checks.

### Monitoring: log groups and alarms (#36)

`enable_monitoring = true` (on in `emulator.tfvars.example`) creates:

- **One CloudWatch log group per ECS service**, `/cloudtrain/<env>/<service>`, kept `log_retention_days`
  (14). That is the only path the shared execution role may write to (#129). Output `log_group_names`
  (service to log group) is for the `awslogs-group` setting in the ECS task definitions.
- **Alarms**, the same as the local Prometheus rules (from Hilal + Adel, `monitoring/aws/README.md` in #115):

| Alarm | Fires when | Local twin |
|---|---|---|
| `<env>-cloudtrain-dead-letters` | `training-jobs-dlq` has any message (1 minute) | `CloudTrainDeadLetters` |
| `<env>-cloudtrain-job-events-not-read` | the oldest `job-events` message is older than 5 minutes, twice in a row | `CloudTrainJobEventsNotRead` |
| `<env>-cloudtrain-server-errors` | more than 5% of requests through the public load balancer answer 5xx (from the services or from the load balancer itself), 5 minutes | `CloudTrainHighErrorRate` |

The server-errors alarm is created once `application-services` passes its load balancer (`alb_arn_suffix`).
Alarms only show in CloudWatch for now (`alarm_actions` is empty). Not here yet: the CloudWatch dashboard and
the "monitor down" alarm, which use Adil's files and `job-events-monitor` from #115 once it merges. On the
emulator these resources are created, but receive no live data (decision 0011); the live view is the local Grafana.

### Service roles for ECS (#35, with Salem; used in #36)

`enable_service_roles = true` (on in `emulator.tfvars.example`) creates one **task role** per service
(`service_task_role_arns`), as `security/DEPLOYMENT_POLICY.md` asks ("one IAM role per service"). The
service's code runs as it. Only these get permissions: `dataset-service` (read/write `datasets`),
`job-service` (send to `training-jobs` and `job-events`, read the dead-letter queue), `scheduler`
(read `training-jobs`), `inference-service` (read `artifacts`), `mlflow` (read/write
`artifacts/mlflow/`). `gateway`, `portal`, `project-service` and `model-registry` call no AWS API, so
their task roles have no permissions.

The **execution role** (ECS pulls the image, writes logs and injects the database secret) is one shared
role in `modules/iam/ecs.tf` (Salem, #129). The database secrets are not created by Terraform:
`scripts/bootstrap-schemas.sh` creates `cloudtrain/<env>/database/<schema>` after the apply (names in
`service_database_secret_names`), so no password is in Terraform state.

### Sun 22 hand-off: services on ECS Fargate (#36, #75)

`enable_application_services = true` creates the ECS cluster **`dev-cloudtrain`**, one Fargate
service per app container (not the training worker), and a public ALB on ports **5810** / **3000**
(HTTP until an ACM certificate exists). Outputs for Salem and the team:

| Output | Who needs it |
|---|---|
| `ecs_cluster_name`, `ecs_service_names` | Salem (deploy #54) |
| `ecs_task_execution_role_arn` | Salem (task definitions) |
| `gateway_url`, `portal_url`, `alb_dns_name` | Everyone (hand-off #75) |

On the emulator set `ecs_desired_count = 0` and `enable_ecs_service_discovery = false` (no images in
emulator ECR; Cloud Map may be missing). With `enable_monitoring = true`, task definitions use
monitoring's log groups (no duplicate create). `alb_arn_suffix` feeds the 5xx alarm. Fatma owns the
2-GPU pool, worker LBs / `worker_urls`, and the monitoring module.

**Emulator gap: security groups.** Right after creating a security group, Terraform removes the
"allow all outbound" rule AWS adds, naming it with ports 0-0. Real AWS ignores ports for an
all-protocols rule; the emulator compares them exactly, answers `InvalidPermission.NotFound`, and
the apply stops. So `emulator.tfvars.example` sets `enable_security_groups = false`: the
`security` module is skipped and the database uses the VPC's default security group, which the
`networking` module locks down (no rules at all). On real AWS leave it `true`. Check again with
each new emulator release, and turn it back on once groups can be created.

**Emulator gap: database schemas.** The emulator's RDS answers like PostgreSQL 17, but it cannot
create schemas: `CREATE SCHEMA` (every form) and schema-qualified tables such as `public.t1` give a
syntax error, and `current_schemas()` does not exist (it looks like SQLite behind a PostgreSQL front).
So `scripts/bootstrap-schemas.sh` stops at its first `CREATE SCHEMA` there and only works on real AWS.
The database outputs (`db_endpoint`, `db_port`, `db_name`, `db_master_secret_arn`) still work, and
services keep using the real PostgreSQL from `make up` for their tables. Found by Mariam on #66.

## Real AWS (after instructors give the account)

```bash
cd infrastructure
cp environments/dev/terraform.tfvars.example environments/dev/terraform.tfvars
# edit unique bucket names + region

cp backends/s3.backend.tf.example backend.tf
cp backends/dev.s3.backend.hcl.example backends/dev.s3.backend.hcl
# edit state bucket

terraform init -migrate-state -backend-config=backends/dev.s3.backend.hcl
terraform apply -var-file=environments/dev/terraform.tfvars
```

## Rules
- Tags on every resource: `Project`, `Environment`, `Owner`.
- Never commit state or secrets.
- `terraform destroy` disposable environments after tests.
- LocalStack is for building/testing only — final demo uses real AWS (RDS/ECS/GPU need it).

## Acceptance test
The group creates the dev environment with Terraform, deploys CloudTrain, changes infrastructure
through Terraform, and safely destroys disposable resources.
