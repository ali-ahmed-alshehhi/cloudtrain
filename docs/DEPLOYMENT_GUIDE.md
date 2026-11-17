# Deployment guide

**Owners:** Hamda + Fatma (Student 6), with Salem (pipeline) and Ali (integration).
How to provision, operate and destroy the CloudTrain cloud environment.

## 1. Before you start
- AWS account, region and budget: _(see docs/OPEN_DECISIONS.md #1 — still open)_
- Tools: Terraform >= 1.6, Docker, AWS CLI
- GPU quota status: request early; approval can take days
- Login: short-lived credentials / IAM roles — no long-lived keys committed

## 2. One-time bootstrap: the state bucket
On **real AWS**, create a dedicated S3 bucket for Terraform state (once per account).
Enable versioning and block public access. Locking uses S3-native `use_lockfile`
(see `infrastructure/backends/s3.backend.tf.example`).

We have no AWS account: the **AWS Emulator** stands in for it
(decision [0011](decisions/0011-aws-emulator-instead-of-aws-account.md)). `infrastructure/bootstrap/`
creates the state bucket on the emulator (versioned, encrypted, private, TLS only), and
`infrastructure/backends/emulator.s3.backend.hcl.example` points the root module at it.
Steps: [infrastructure/bootstrap/README.md](../infrastructure/bootstrap/README.md).

## 3. Create an environment (`dev`, `staging`)

### 3a. AWS Emulator (our stand-in for an AWS account — decision 0011)

```bash
cd infrastructure
./scripts/emulator-up.sh
source ./scripts/emulator-env.sh        # every new terminal needs this again
terraform init
terraform plan  -var-file=environments/dev/emulator.tfvars.example
terraform apply -var-file=environments/dev/emulator.tfvars.example
terraform output
```

Creates the whole dev environment: VPC with public and private subnets and NAT (our security
groups are skipped on the emulator because of an emulator gap, see `infrastructure/README.md`);
S3 `datasets` + `artifacts`; SQS `training-jobs` (+ DLQ) + `job-events`; one ECR repository per
service; RDS PostgreSQL 17 with its master secret in Secrets Manager. `terraform output` lists
what each teammate needs (see the hand-off table in `infrastructure/README.md`).

Skip `scripts/bootstrap-schemas.sh` on the emulator: the database endpoint lives inside the
emulator container and is not published to your laptop. Services keep using `make up`
(LocalStack + local Postgres) for their own work.

Stop when done:

```bash
terraform destroy -var-file=environments/dev/emulator.tfvars.example
./scripts/emulator-down.sh
```

> LocalStack still works for Terraform (`docker-compose.localstack.yml` +
> `environments/dev/localstack.tfvars.example`), but the team uses the emulator.

### 3b. Real AWS

```bash
cd infrastructure
cp environments/dev/terraform.tfvars.example environments/dev/terraform.tfvars
# edit region + globally unique bucket names

cp backends/s3.backend.tf.example backend.tf
cp backends/dev.s3.backend.hcl.example backends/dev.s3.backend.hcl
# edit state bucket

terraform init -migrate-state -backend-config=backends/dev.s3.backend.hcl
terraform plan  -var-file=environments/dev/terraform.tfvars
terraform apply -var-file=environments/dev/terraform.tfvars
```

### 3c. Database schemas (after first RDS apply)

```bash
# Requires network path to private RDS + aws CLI + psql + jq
ENVIRONMENT=dev ./scripts/bootstrap-schemas.sh
```

Creates roles/schemas: `projects`, `datasets`, `jobs`, `scheduler`, `registry`, `mlflow`
(same as local `make up`). Store each service password in Secrets Manager for deploy.
Service connection strings should use `?sslmode=require` because RDS forces SSL.

## 4. Deploy the services
Images → ECR, services → ECS Fargate: Salem's pipeline. Hamda + Fatma provide ECR URLs and
network/security group IDs via `terraform output`.

## 5. Change something through Terraform
Example: change `sqs_visibility_timeout_seconds` in tfvars → `terraform plan` → `terraform apply`.

## 6. Operate
- Logs/dashboards: CloudWatch (module still a stub)
- Job cost: `contracts/pricing.yaml`
- Stuck worker: Maitha + this guide

## 7. Destroy

```bash
# LocalStack
terraform destroy -var-file=environments/dev/localstack.tfvars.example
docker compose -f docker-compose.localstack.yml down

# Real AWS
terraform destroy -var-file=environments/dev/terraform.tfvars
```

Keep the **state bucket** on real AWS. Destroy disposable `dev` resources after tests and after submission.

## 8. Cost notes
- NAT Gateway and idle GPU instances cost money on real AWS.
- LocalStack practice costs $0 (no AWS account required).
- Tag every resource with `Project`, `Environment`, `Owner`.

## Hand-off values (after apply)

| Output | Who needs it |
|---|---|
| `datasets_bucket` | Faisal |
| `artifacts_bucket` | Abdullah, Majed |
| `training_jobs_queue_url` | Mariam (write), Maitha (read) |
| `job_events_queue_url` | Mariam / notifications |
| `ecr_repository_urls` | Salem |
| `vpc_id` / subnet IDs / security groups | Maitha, Salem, Majed |
| `db_endpoint` | Service owners (DATABASE_URL) |
| `db_master_secret_arn` | Hamda/Fatma + deploy pipeline |
