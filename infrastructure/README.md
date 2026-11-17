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
| `database` | RDS Postgres + Secrets Manager (enable on real AWS) |
| `iam` / `application-services` / `training-compute` / `monitoring` | stubs — next |

### Next-week apply (real AWS, Wed 18 hand-off)

```bash
# In terraform.tfvars (not committed):
enable_networking         = true
enable_container_registry = true
enable_database           = true

terraform apply -var-file=environments/dev/terraform.tfvars
./scripts/bootstrap-schemas.sh   # one-time schemas for Faisal/Mariam/…
terraform output                 # share db_endpoint + buckets + queues + ecr
```

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
