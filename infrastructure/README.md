# Terraform cloud infrastructure — `infrastructure/`

| Owners (partners) | Port | Contracts |
|---|---|---|
| Hamda + Fatma (Student 6) | — | `contracts/pricing.yaml`, the cloud mapping in `docs/ARCHITECTURE.md` |

## What it must do
Create **every** cloud resource with Terraform (nothing by hand): network, storage, database, queues,
container registry, the services' deployment, CPU/GPU training machines, monitoring and IAM.
Remote state in S3 with locking and restricted access. Dev and staging environments. Tagging and cost
visibility. Deploy and clean-up docs in `docs/DEPLOYMENT_GUIDE.md`. Prices in `contracts/pricing.yaml`.

## Cloud mapping

| Part | AWS |
|---|---|
| Services, gateway, portal | ECS Fargate (stateless services) |
| Images | ECR |
| Training workers | EC2 CPU / **GPU** instances or AWS Batch, started per job (**GPU training never runs on Fargate**) |
| Database | RDS PostgreSQL (one schema per service) |
| Files | S3 buckets `datasets` and `artifacts` |
| Queues | SQS `training-jobs` (+ `training-jobs-dlq` redrive), `job-events`, all encrypted |
| Login | Cognito or external OIDC |
| Secrets | Secrets Manager |
| Logs and metrics | CloudWatch (+ Prometheus/Grafana) |
| Network | VPC: gateway and portal behind a load balancer in public subnets, everything else in private subnets |

## What is built in this PR (starter)

| Module | Status |
|---|---|
| `networking` | VPC, public/private subnets, IGW, optional NAT |
| `security` | ALB / services / workers / database security groups |
| `object-storage` | S3 `datasets` + `artifacts` (encrypted, private) |
| `message-queue` | SQS `training-jobs` + DLQ + `job-events` |
| `container-registry` | ECR repos per service image |
| `database` / `iam` / `application-services` / `training-compute` / `monitoring` | still stubs — next |

## Practice on LocalStack (no AWS account yet)

```bash
cd infrastructure
docker compose -f docker-compose.localstack.yml up -d   # host port 4568

export AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1
terraform init
terraform plan  -var-file=environments/dev/localstack.tfvars.example
terraform apply -var-file=environments/dev/localstack.tfvars.example
terraform output
terraform destroy -var-file=environments/dev/localstack.tfvars.example
```


This creates the same bucket/queue **names** the rest of the team uses in `.env.example`.
(Endpoint in the example file is `http://localhost:4568`.)

## Real AWS (after the instructors give the account)

```bash
cd infrastructure
cp environments/dev/terraform.tfvars.example environments/dev/terraform.tfvars
# edit unique bucket names + region

cp backends/s3.backend.tf.example backend.tf
cp backends/dev.s3.backend.hcl.example backends/dev.s3.backend.hcl
# edit state bucket (created once — see docs/DEPLOYMENT_GUIDE.md)

terraform init -migrate-state -backend-config=backends/dev.s3.backend.hcl
terraform plan  -var-file=environments/dev/terraform.tfvars
terraform apply -var-file=environments/dev/terraform.tfvars
```


Share `terraform output` values with Faisal, Mariam, Maitha and Salem.

## Rules
- Every resource is tagged `Project`, `Environment`, `Owner` (set once in `providers.tf`).
- State and secrets are **never** committed (`*.tfstate` and `*.tfvars` are in `.gitignore`).
- GPU machines run only while a job runs.
- Encryption and least-privilege IAM everywhere.
- `terraform destroy` on disposable environments after each test session.

## Mandatory demos (with the class)
1. `terraform apply` creates the dev environment.
2. Inspect the execution plan.
3. Deploy the services into it.
4. Change a parameter (e.g. worker capacity).
5. Apply the change without rebuilding by hand.
6. Show state and dependency management.
7. `terraform destroy` the disposable resources safely.

## Acceptance test
The group creates the dev environment with Terraform, deploys CloudTrain, changes infrastructure
through Terraform, and safely destroys disposable resources.
