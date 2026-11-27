# Module: application-services

Owners: Hamda + Fatma.

ECS Fargate services for the gateway, portal and stateless services, behind the public load balancer (#36).

## What it creates

| Resource | Name / note |
|---|---|
| ECS cluster | `<environment>-cloudtrain` (required by Salem's deploy role in #129) |
| Fargate services | gateway, portal, project-service, dataset-service, job-service, scheduler, model-registry, inference-service, mlflow, job-events-monitor (port 8011, not behind the load balancer, #135) |
| Public ALB | gateway on **5810**, portal on **3000** (and :80 → gateway) |
| Log groups | `/cloudtrain/<environment>/<service>` until the monitoring module owns them |
| Service discovery | optional private DNS `<service>.<environment>.cloudtrain.local` |

Training workers stay on EC2 Auto Scaling (decision 0012), not Fargate.

## Inputs you need from other modules

- `execution_role_arn` — `modules/iam` (#129)
- `task_role_arns` — `modules/service-roles` (#128)
- `ecr_repository_urls` — `modules/container-registry`
- `log_group_names` — from monitoring when Fatma's module lands (optional; we create them if empty)
- `database_secret_names` — from service-roles / `bootstrap-schemas.sh`
- `worker_urls_json` — from Fatma's worker LBs when ready (`TRAINING_WORKER_URLS`)

## Emulator notes

- Set `desired_count = 0` until images exist in ECR (emulator ECR refuses uploads; images are on ghcr.io today).
- `enable_security_groups = false` on the emulator: pass the VPC default security group.
- Turn off `enable_service_discovery` if Cloud Map is missing on the stand-in.

## Deploy

Salem's pipeline registers new task definition revisions with the commit image tag and updates services. This module's `lifecycle.ignore_changes` on `task_definition` / `desired_count` keeps Terraform from fighting the pipeline.
