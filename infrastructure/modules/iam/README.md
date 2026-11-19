# Module: iam

Owners: Hamda + Fatma.

Least-privilege roles for each service and worker (with Salem).

## ECS roles (`ecs.tf`, drafted by Salem for #36 / #54)
On when `enable_ecs_roles = true` (both dev tfvars examples).

| Role | Used by | Can | Cannot |
|---|---|---|---|
| `<env>-cloudtrain-ecs-task-execution` | ECS, to start every task (`executionRoleArn`) | pull **our** 10 images, write logs under `/cloudtrain/<env>/`, read the secrets the task definition injects (the database master secret) | anything the service code does: that is the per-service task role (#36) |
| `<env>-cloudtrain-github-deploy` | GitHub Actions, via **OIDC** (no AWS keys in GitHub) | push our images, register task definitions, update services in `<env>-cloudtrain`, pass only the execution and task roles to ECS | create or delete infrastructure; be used by a pull request or another branch (only `main` and the `staging` / `production` environments) |

Outputs: `ecs_task_execution_role_arn` (for every task definition) and `github_deploy_role_arn`
(repository variable `AWS_DEPLOY_ROLE_ARN`). The cluster must be named `<env>-cloudtrain`.
