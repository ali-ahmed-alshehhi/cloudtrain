# Deployment guide

**Owners:** Hamda + Fatma (Student 6), with Salem (pipeline) and Ali (integration).
How to provision, operate and destroy the CloudTrain cloud environment.

## 1. Before you start
- **No AWS account:** the instructors asked us to use the **AWS Emulator** instead (decision
  [0011](decisions/0011-aws-emulator-instead-of-aws-account.md)). Everything below runs on a laptop.
  The same Terraform runs on real AWS later (section 3b).
- **Tools:** Terraform **1.10 or newer** (S3-native state locking, `use_lockfile`), Docker with about
  2 GB free memory for the emulator, AWS CLI.
- **No GPU quota needed:** the emulator starts no real machines, so no real GPU runs (decision 0011).
- **Credentials:** `scripts/emulator-env.sh` points the AWS CLI and Terraform at the emulator. Never use
  real AWS keys with it, and never commit keys, `.env`, state files or `backend.tf`.

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

Creates the whole dev environment (126 resources on `main`, 22 Nov 2026):

- **Network:** VPC with public and private subnets and NAT. Our security groups are skipped on the
  emulator because of an emulator gap (see `infrastructure/README.md`).
- **Storage and queues:** S3 `datasets` + `artifacts`; SQS `training-jobs` (+ `training-jobs-dlq`)
  + `job-events`.
- **Images and database:** one ECR repository per service (keeps the last 20 images); RDS PostgreSQL 17
  with an RDS-managed master secret.
- **Login:** Cognito user pool, portal app client and role groups (decision 0006).
- **Permissions:** one task role per service, the shared ECS execution role, the GitHub deploy role.
- **GPU workers:** two Auto Scaling groups, `gpu-1` (`g4dn.xlarge`, 1 GPU) and `gpu-4` (`g4dn.12xlarge`,
  4 GPUs), each with an internal load balancer on port 8010 (decision 0012).
- **Services:** ECS cluster `dev-cloudtrain` with one Fargate service per service, behind a public load
  balancer (gateway on 5810, portal on 3000).
- **Monitoring:** one CloudWatch log group per service, `/cloudtrain/<env>/<service>`, and alarms.

`terraform output` lists what each teammate needs (table at the end of this guide).

Skip `scripts/bootstrap-schemas.sh` on the emulator: its RDS cannot create schemas (`CREATE SCHEMA`
gives a syntax error, see "Emulator gap: database schemas" in `infrastructure/README.md`), so the
script only works on real AWS. Services keep using `make up` (LocalStack + local Postgres) for their
own work.

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
# Requires network path to private RDS + aws CLI + psql + jq + openssl + terraform
# Host/port come from terraform outputs (RDS-managed secret has only username/password).
cd infrastructure
export MASTER_SECRET_ARN="$(terraform output -raw db_master_secret_arn)"
# Optional overrides if outputs are unavailable:
# export DB_HOST=... DB_PORT=5432 DB_NAME=cloudtrain
ENVIRONMENT=dev ./scripts/bootstrap-schemas.sh
```

Creates roles/schemas: `projects`, `datasets`, `jobs`, `scheduler`, `registry`, `mlflow`
(same as local `make up`). Writes each service `DATABASE_URL` to Secrets Manager as
`cloudtrain/<env>/database/<service>` (passwords are not printed). Every URL ends with
`?sslmode=require` because RDS forces SSL (`rds.force_ssl`).

## 4. Deploy the services
Terraform creates the **place** the services run; Salem's pipeline puts the **images** in it.

- **Terraform (Hamda, #135):** ECS cluster `dev-cloudtrain`, one Fargate service and task definition per
  service, a public load balancer (gateway on 5810, portal on 3000), each service with its own task role
  (#128), the shared execution role (#129), its own `DATABASE_URL` secret and its log group (#134). The
  Scheduler gets `TRAINING_WORKER_URLS` from `worker_urls`. The training workers stay on EC2, not Fargate.
- **Pipeline (Salem, #54):** builds the images, pushes them, registers a new task definition revision with
  the commit's image tag and updates the services. Terraform ignores `task_definition` and `desired_count`
  after creation, so a later `terraform apply` doesn't roll a deploy back.
- **On the emulator:** `ecs_desired_count = 0`. The services exist but run no tasks, because the emulator's
  ECR refuses image uploads (images are on ghcr.io today). Services keep using `make up` for their work.

Check after `terraform apply`:

```bash
terraform output ecs_cluster_name          # dev-cloudtrain
terraform output ecs_service_names         # the 9 services
aws ecs list-services --cluster dev-cloudtrain
terraform output gateway_url               # the public address of the gateway
```

Emulator quirk: its load balancer address is `127.0.0.1:<port>`, so `gateway_url` and `portal_url` look like
`http://127.0.0.1:32863:5810`. On real AWS the address is a host name and the URLs are right.

## 5. Change something through Terraform
The worker capacity is a variable (demo 4). To run two 1-GPU workers instead of one:

```bash
terraform plan  -var-file=environments/dev/emulator.tfvars.example -var worker_desired_capacity=2
terraform apply -var-file=environments/dev/emulator.tfvars.example -var worker_desired_capacity=2
```

Expected: the plan shows `~ desired_capacity = 1 -> 2` and `Plan: 0 to add, 1 to change, 0 to destroy`.
The Auto Scaling group starts the extra machine and registers it in the pool's load balancer by itself;
nothing is rebuilt by hand. To keep the change, edit the value in your tfvars file instead of using `-var`.

| Pool | Size variable | Upper limit | Machine |
|---|---|---|---|
| `gpu-1` | `worker_desired_capacity` | `worker_max_size` (2) | `g4dn.xlarge`, 1 GPU |
| `gpu-4` | `multi_gpu_desired_capacity` | `multi_gpu_max_size` (1) | `g4dn.12xlarge`, 4 GPUs |

Any other variable works the same way (for example `sqs_visibility_timeout_seconds`): change it, read
the plan, apply.

## 6. Operate
- **Worker addresses:** `terraform output worker_urls` (machine type to load balancer address). The
  Scheduler reads it as `TRAINING_WORKER_URLS` (#70).
- **Logs:** each service writes to its CloudWatch log group, `/cloudtrain/<env>/<service>`
  (`terraform output log_group_names`), kept 14 days.
- **Alarms** (`terraform output alarm_names`): dead letters on `training-jobs-dlq`, `job-events` not read
  for 5 minutes, more than 5% 5xx through the public load balancer. They show in CloudWatch; nobody is
  notified yet. On the emulator they get no live data; the live view is the local Grafana (#109).
- **A job failed 3 times:** it is on `training-jobs-dlq` (kept 14 days). Mariam's dead-letter reader
  retries it.
- **Job cost:** hourly prices in `contracts/pricing.yaml` × machine time. The portal labels it
  "Estimated cost", not a bill.
- **Stuck worker:** Maitha's Scheduler frees the slot (#102); scale the pool with section 5 if needed.

## 7. Destroy
Always look at the plan first, then destroy:

```bash
# AWS Emulator (what we use)
terraform plan -destroy -var-file=environments/dev/emulator.tfvars.example   # read what goes
terraform destroy       -var-file=environments/dev/emulator.tfvars.example
terraform state list | wc -l                                                 # expect 0
./scripts/emulator-down.sh

# Real AWS
terraform plan -destroy -var-file=environments/dev/terraform.tfvars
terraform destroy       -var-file=environments/dev/terraform.tfvars
```

- `destroy` removes only the `dev` environment. The **state bucket** has its own state in
  `infrastructure/bootstrap/` and is not touched; keep it on real AWS.
- If you use the remote state bucket, run `git restore backend.tf && terraform init -reconfigure`
  before committing anything. `backend.tf` is never committed.
- Destroy disposable `dev` resources after every test and after submission.

## 8. Cost notes (real AWS, us-east-1, on-demand)
The emulator costs nothing. On real AWS the expensive parts are the GPU machines and the NAT gateway:

| Item | Price | Note |
|---|---|---|
| `g4dn.xlarge` (1 GPU) | $0.526 / hour | `contracts/pricing.yaml` |
| `g4dn.12xlarge` (4 GPUs) | $3.912 / hour | `contracts/pricing.yaml`; also runs 2-GPU jobs |
| `g4dn.metal` (8 GPUs) | $7.824 / hour | `contracts/pricing.yaml`; not built by Terraform |
| NAT gateway | about $0.045 / hour + data | check the AWS price page before quoting |

- Both GPU pools default to **0 machines** in code (the emulator tfvars set 1 for `gpu-1`), and the
  upper limits (`worker_max_size`, `multi_gpu_max_size`) stop a typo from starting many GPU machines.
- Every resource is tagged `Project`, `Environment`, `Owner`.
- Prices change: check them again before quoting them in the final report.

## 9. The Terraform demos (runbook)
The seven mandatory demos, on the emulator. Start with `./scripts/emulator-up.sh` and
`source ./scripts/emulator-env.sh`, from `infrastructure/`. `V=environments/dev/emulator.tfvars.example`.

| # | Demo | Commands | What to show |
|---|---|---|---|
| 1 | Apply creates dev | `terraform init` then `terraform apply -var-file=$V` | `Apply complete! Resources: 126 added` (on `main`, 22 Nov), then `terraform output` |
| 2 | Inspect the plan | `terraform plan -var-file=$V -out=dev.tfplan` then `terraform show dev.tfplan` | `+` create, `~` change in place, `-` destroy; the summary line |
| 3 | Deploy the services | `terraform output ecs_cluster_name`, `terraform output ecs_service_names`, `aws ecs list-services --cluster dev-cloudtrain` | `dev-cloudtrain` and its 9 services behind the load balancer (section 4). On the emulator they run 0 tasks (no images in its ECR); Salem's pipeline does the image rollout |
| 4 | Change a parameter | `terraform plan -var-file=$V -var worker_desired_capacity=2` | `~ desired_capacity = 1 -> 2`, `0 to add, 1 to change, 0 to destroy` |
| 5 | Apply it, no manual rebuild | `terraform apply -var-file=$V -var worker_desired_capacity=2`, then `aws autoscaling describe-auto-scaling-groups --auto-scaling-group-names dev-cloudtrain-gpu-1 --query 'AutoScalingGroups[0].[DesiredCapacity,length(Instances)]'` | `2 2`; a new plan says `No changes` |
| 6 | State and dependencies | `terraform state list`; `terraform state show 'module.training_compute_gpu[0].aws_autoscaling_group.worker'`; `terraform graph \| dot -Tsvg > graph.svg` (needs Graphviz: `brew install graphviz`) | every resource Terraform manages; how the workers depend on the network, the IAM role and the queues |
| 7 | Destroy safely | `terraform plan -destroy -var-file=$V`, then `terraform destroy -var-file=$V`, then `terraform state list \| wc -l` | `Destroy complete!`, state empty, the state bucket untouched |

Optional 8th demo: the Pulumi layer (section 10), between demo 6 and demo 7.

Rehearsed on 22 Nov 2026 on `main`: all seven worked (126 created; demo 4 changed 1 resource; `terraform
state list` showed 140 entries, resources plus data sources; destroy removed 126 and left the state empty).

Say during the demo: the emulator starts no real machines, so GPU speed is "not measured on AWS"
(decision 0011); the Terraform is the same for real AWS (section 3b).

## 10. The Pulumi layer: CloudWatch dashboard (optional 8th demo)
Terraform creates every resource; a small Pulumi program above it creates **only** the CloudWatch
dashboard, from Terraform's outputs (decision [0013](decisions/0013-pulumi-layer-above-terraform.md)).
Setup once and all settings: [infrastructure/pulumi/README.md](../infrastructure/pulumi/README.md).

After demo 1 (Terraform applied, emulator running), from `infrastructure/pulumi/`:

```bash
source ../scripts/emulator-env.sh
export PULUMI_CONFIG_PASSPHRASE='<your own passphrase>'
terraform -chdir=.. output -json > tf-outputs.json   # Pulumi reads Terraform, never the other way round
pulumi preview                                      # + 3 to create (stack, AWS provider, dashboard)
pulumi up --yes
pulumi stack output                                 # dashboard_name = dev-cloudtrain, widget_count = 5
terraform -chdir=.. plan -var-file=environments/dev/emulator.tfvars.example   # No changes: Pulumi touched nothing of Terraform's
```

**Destroy order:** `pulumi destroy --yes` first, then demo 7 (`terraform destroy`). The dashboard points at
Terraform's resources, so it goes before them.

Say during the demo: Pulumi is a layer on top, not a replacement; it owns one resource, and the seven
Terraform demos work with or without it.

## Hand-off values (after apply)

| Output | Who needs it |
|---|---|
| `datasets_bucket` | Faisal |
| `artifacts_bucket` | Abdullah, Majed |
| `training_jobs_queue_url`, `training_jobs_dlq_url` | Mariam (write, read the DLQ), Maitha (only reader of `training-jobs`) |
| `job_events_queue_url` | Mariam, workers (write); `job-events-monitor` (read) |
| `ecr_repository_urls` | Salem |
| `db_endpoint`, `db_address`, `db_port`, `db_name`, `db_master_secret_arn` | bootstrap script; service owners via their `DATABASE_URL` secret |
| `service_database_secret_names` | ECS task definitions (each service's own `DATABASE_URL`) |
| `jwt_issuer`, `jwt_audience`, `jwt_jwks_url`, `cognito_user_pool_id` | Ali (gateway), Salem (login), portal |
| `worker_urls`, `gpu_worker_autoscaling_group`, `multi_gpu_worker_autoscaling_group` | Maitha (Scheduler), Ahmed + Abdulla, Abdullah |
| `service_task_role_arns`, `ecs_task_execution_role_arn`, `github_deploy_role_arn` | Hamda (ECS), Salem (deploy) |
| `ecs_cluster_name`, `ecs_service_names` | Salem (deploy, #54) |
| `gateway_url`, `portal_url`, `alb_dns_name` | everyone (the public addresses) |
| `log_group_names`, `alarm_names` | monitoring; Hilal + Adel |
| `vpc_id`, subnet IDs, security group IDs | Hamda, Salem, Maitha |
