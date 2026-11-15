# Terraform cloud infrastructure — `infrastructure/`

| Owners (partners) | Port | Contracts |
|---|---|---|
| Hamda + Fatma (Student 6) | — | `contracts/pricing.yaml`, the cloud mapping in `docs/ARCHITECTURE.md` |

## What it must do
Create **every** cloud resource with Terraform (nothing by hand): network, storage, database, queues,
container registry, the services' deployment, CPU/GPU training machines, monitoring and IAM.
Remote state in S3 with locking and restricted access. Dev and staging environments. Tagging and cost
visibility. Deploy and clean-up docs in `docs/DEPLOYMENT_GUIDE.md`. Prices in `contracts/pricing.yaml`.

## Practice AWS account (Student 6) — official AWS Emulator

We use the **official** [AWS Emulator](https://github.com/aws/aws-emulator) as our local fake AWS account
for Terraform practice. This does **not** replace the app LocalStack in the root `docker-compose.yml`
(that stays for Faisal/Mariam/`make up`).

```bash
cd infrastructure
./scripts/emulator-up.sh          # build + start https://127.0.0.1:9297
source ./scripts/emulator-env.sh  # point AWS CLI / Terraform at the emulator
terraform init
terraform plan  -var-file=environments/dev/emulator.tfvars.example
terraform apply -var-file=environments/dev/emulator.tfvars.example
terraform output
terraform destroy -var-file=environments/dev/emulator.tfvars.example
./scripts/emulator-down.sh
```

Creates the same names teammates already use: `datasets`, `artifacts`, `training-jobs`,
`training-jobs-dlq`, `job-events`.

Docs: [Getting started with Docker](https://docs.aws.amazon.com/emulator/latest/userguide/getting-started-docker.html) ·
[Point SDK at emulator](https://docs.aws.amazon.com/emulator/latest/userguide/point-sdk-to-emulator.html)

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
- Emulator is for building/testing only — final demo uses real AWS.

## Acceptance test
The group creates the dev environment with Terraform, deploys CloudTrain, changes infrastructure
through Terraform, and safely destroys disposable resources.
