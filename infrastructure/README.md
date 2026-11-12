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

## Rules
- Every resource is tagged `Project`, `Environment`, `Owner` (set once in `providers.tf`).
- State and secrets are **never** committed (`*.tfstate` and `*.tfvars` are in `.gitignore`).
- GPU machines run only while a job runs.
- Encryption and least-privilege IAM everywhere.
- `terraform destroy` on disposable environments after each test session.

## Layout (from the brief)
```text
infrastructure/
├── environments/
│   ├── dev/
│   └── staging/
├── modules/
│   ├── networking/  security/  database/  object-storage/  message-queue/
│   ├── container-registry/  application-services/  training-compute/
│   └── monitoring/  iam/
├── backend.tf  providers.tf  variables.tf  outputs.tf
```

## Mandatory demos (with the class)
1. `terraform apply` creates the dev environment.
2. Inspect the execution plan.
3. Deploy the services into it.
4. Change a parameter (e.g. worker capacity).
5. Apply the change without rebuilding by hand.
6. Show state and dependency management.
7. `terraform destroy` the disposable resources safely.

## Endpoints
None: this folder creates cloud resources; it runs no service.

## Acceptance test
The group creates the dev environment with Terraform, deploys CloudTrain, changes infrastructure
through Terraform, and safely destroys disposable resources.
