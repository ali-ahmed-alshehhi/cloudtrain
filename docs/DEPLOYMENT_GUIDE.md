# Deployment guide

**Owners:** Hamda + Fatma (Student 6), with Salem (pipeline) and Ali (integration).
How to provision, operate and destroy the CloudTrain cloud environment.

## 1. Before you start
- AWS account, region and budget: _(see docs/OPEN_DECISIONS.md #1 — still open)_
- Tools: Terraform >= 1.6, AWS CLI, Docker (for LocalStack practice)
- GPU quota status: request early; approval can take days
- Login: use short-lived credentials / IAM roles — no long-lived keys committed

## 2. One-time bootstrap: the state bucket
On **real AWS**, create a dedicated S3 bucket for Terraform state (once per account), e.g.
`cloudtrain-tfstate-<account>`. Enable versioning and block public access. Locking uses S3-native
`use_lockfile` (see `infrastructure/backend.tf`).

Document the bucket name for the team; put it in your private `backends/dev.s3.backend.hcl`
(never commit the filled file if it is account-specific and sensitive).

Until the AWS account exists, practice with LocalStack (default `backend.tf` stores state locally).


## 3. Create an environment (`dev`, `staging`)

### 3a. LocalStack practice (today)

```bash
cd infrastructure
docker compose -f docker-compose.localstack.yml up -d   # publishes localhost:4568
export AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1
terraform init
terraform plan  -var-file=environments/dev/localstack.tfvars.example
terraform apply -var-file=environments/dev/localstack.tfvars.example
terraform output
```

Creates: S3 `datasets` + `artifacts`, SQS `training-jobs` (+ DLQ) + `job-events`.

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


What `plan` should show (starter): VPC/subnets (if enabled), security groups, two S3 buckets,
three SQS queues, ECR repositories.

## 4. Deploy the services
_Images → ECR, services → ECS Fargate: Salem's pipeline. Hamda + Fatma provide ECR URLs and
network/security group IDs via `terraform output`._

## 5. Change something through Terraform
Example (later, when `training-compute` exists): change worker capacity in tfvars →
`terraform plan` → `terraform apply`. No console clicks.

For now, you can demo a small change such as `sqs_visibility_timeout_seconds`.

## 6. Operate
- Logs/dashboards: CloudWatch (module still a stub)
- Job cost: `contracts/pricing.yaml` (fill real region prices)
- Stuck worker: Maitha + this guide (release / terminate instance)

## 7. Destroy

```bash
# LocalStack
terraform destroy -var-file=environments/dev/localstack.tfvars.example

# Real AWS
terraform destroy -var-file=environments/dev/terraform.tfvars
```

Keep the **state bucket**. Destroy disposable `dev` resources after test sessions and after submission.

## 8. Cost notes
- NAT Gateway and idle GPU instances cost money — NAT only on real AWS; GPUs only while a job runs.
- LocalStack practice costs $0.
- Tag every resource with `Project`, `Environment`, `Owner` for cost reports.

## Hand-off values (after apply)

Give teammates these outputs (names stay stable):

| Output | Who needs it |
|---|---|
| `datasets_bucket` | Faisal |
| `artifacts_bucket` | Abdullah, Majed |
| `training_jobs_queue_url` | Mariam (write), Maitha (read) |
| `job_events_queue_url` | Mariam / notifications |
| `ecr_repository_urls` | Salem |
| `vpc_id` / subnet IDs / security groups | Maitha, Salem, Majed |
