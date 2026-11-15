# Terraform cloud infrastructure — `infrastructure/`

| Owners (partners) | Port | Contracts |
|---|---|---|
| Hamda + Fatma (Student 6) | — | `contracts/pricing.yaml`, the cloud mapping in `docs/ARCHITECTURE.md` |

## What it must do
Create **every** cloud resource with Terraform (nothing by hand): network, storage, database, queues,
container registry, the services' deployment, CPU/GPU training machines, monitoring and IAM.
Remote state in S3 with locking and restricted access. Dev and staging environments. Tagging and cost
visibility. Deploy and clean-up docs in `docs/DEPLOYMENT_GUIDE.md`. Prices in `contracts/pricing.yaml`.

## Practice on LocalStack (Student 6)

Terraform practice uses **LocalStack** — the same tool as the app (`docker-compose.yml`, decision
[0005](../docs/decisions/0005-localstack-for-s3.md) / [0009](../docs/decisions/0009-terraform-local-uses-localstack.md)).
We do **not** run a second AWS emulator.

```bash
cd infrastructure
docker compose -f docker-compose.localstack.yml up -d
export AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1
terraform init
terraform plan  -var-file=environments/dev/localstack.tfvars.example
terraform apply -var-file=environments/dev/localstack.tfvars.example
terraform output
terraform destroy -var-file=environments/dev/localstack.tfvars.example
docker compose -f docker-compose.localstack.yml down
```

Creates the same names teammates already use: `datasets`, `artifacts`, `training-jobs`,
`training-jobs-dlq`, `job-events`.

> The small compose file only publishes host port `4568` so Terraform can reach LocalStack from the
> laptop. Image pin matches root compose: `localstack/localstack:4.14`.

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
| `database` / `iam` / `application-services` / `training-compute` / `monitoring` | stubs — next |

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
