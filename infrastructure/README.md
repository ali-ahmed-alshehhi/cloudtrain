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
| `iam` / `application-services` / `training-compute` / `monitoring` | stubs — next |

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
| `vpc_id`, `private_subnet_ids`, `services_security_group_id` | the network services and workers run in (the security group is empty on the emulator, see below) | Hamda + Fatma (ECS, training machines); Maitha |

On the emulator these addresses point at the emulator, not at AWS, so services keep using
`make up` for their own work. The names match `.env.example`, so nothing changes in service code
if a real AWS account appears later.

**Emulator gap: security groups.** Right after creating a security group, Terraform removes the
"allow all outbound" rule AWS adds, naming it with ports 0-0. Real AWS ignores ports for an
all-protocols rule; the emulator compares them exactly, answers `InvalidPermission.NotFound`, and
the apply stops. So `emulator.tfvars.example` sets `enable_security_groups = false`: the
`security` module is skipped and the database uses the VPC's default security group, which the
`networking` module locks down (no rules at all). On real AWS leave it `true`. Check again with
each new emulator release, and turn it back on once groups can be created.

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
