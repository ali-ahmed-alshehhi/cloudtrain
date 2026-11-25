# Deployment policy: environments, approval, rollback, secrets

Owner: Salem (Student 9). In force on `main` since 22 Nov (deploy pipeline #151). Changes to this
file: pull request reviewed by Ali.

## Environments
| Environment | Where | How code gets there | Who can deploy | Data |
|---|---|---|---|---|
| **local** | each laptop, `docker compose` | `make up` | anyone | fake values from `.env.example`, `AUTH_MODE=dev` |
| **CI** | GitHub Actions, thrown away after each run | every pull request and push | automatic | fake values |
| **staging** | AWS (today the AWS Emulator) | **automatically** after a merge to `main` passes CI and its images pass the Trivy gate | the pipeline only | test data, real login (`AUTH_MODE=jwt`) |
| **production** (the demo) | AWS (today the AWS Emulator) | **promotion** of an image already tested on staging, after **approval** | the pipeline only, after Ali or Salem approves | demo data, real login |

Terraform has `dev` and `staging` folders: `dev` is Hamda + Fatma's playground for Terraform changes
and is what the pipeline builds on the emulator today; with an AWS account staging and production
each get their own cluster (repository variables `STAGING_CLUSTER`, `PRODUCTION_CLUSTER`).

## Where the images are (task #52)
`.github/workflows/images.yml` builds the 10 images, refuses any with a CRITICAL vulnerability that
has a fix, and pushes each one tagged with its commit (`gateway:4999c59`) on every push to `main`.

- **Today: GitHub Container Registry**, `ghcr.io/ali-ahmed-alshehhi/cloudtrain/<service>:<commit>`.
  There is no AWS account (decision 0011), and the AWS Emulator's ECR keeps repositories and rules
  but refuses image uploads ("the operation is unsupported", checked in CI on 18 Nov). The run uses
  its own short-lived token: no password is stored.
- **With an AWS account:** set the repository variables `AWS_DEPLOY_ROLE_ARN` and `AWS_REGION`. The
  same workflow signs in with GitHub OIDC and pushes to ECR (`cloudtrain/dev/<service>`). Nothing
  else changes.

## The deploy pipeline (task #54)
`.github/workflows/deploy.yml` with `.github/deploy/deploy.sh`:

1. **Staging**, automatically after `images.yml` pushed a commit's images on `main`: copy each
   service's running task definition, change **only** the image to `<service>:<commit>`, register
   it as a new revision and switch the service. Then a **smoke test** runs those exact images with
   the demo walk-through (`make e2e`).
2. **Production**, the same images, after a reviewer approves the GitHub environment
   `production` (Settings → Environments → production → Required reviewers: Ali, Salem).
3. **Rollback**, see below.

Today it runs on the AWS Emulator (decision 0011): each job starts the emulator and builds the dev
environment with Terraform, so staging and production are separate runs of it, told apart by the
approval gate; services run no tasks there (`ecs_desired_count = 0`). With an AWS account, set the
repository variables `AWS_DEPLOY_ROLE_ARN`, `STAGING_CLUSTER` and `PRODUCTION_CLUSTER`: the same
jobs sign in with GitHub OIDC and wait until every service passes its `/health` check.

## Rules
1. **Nobody deploys from a laptop** to staging or production. Only the pipeline does, with a GitHub
   OIDC role: GitHub stores **no AWS keys**.
2. **Build once, deploy the same image.** Each image is tagged with the Git commit (e.g.
   `gateway:4999c59`). Production receives exactly the image that passed on staging. Never `latest`.
3. **Only `main` can deploy.** Branches and pull requests are tested, never deployed.
4. **Approval:** the GitHub environment `production` requires one approval from **Ali or Salem**
   (set as required reviewers). The deploy waits on the run page (*Review deployments*) until
   someone clicks *Approve*. While it waits, newer commits still deploy to staging: each
   environment has its own queue, and the newest waiting production deploy replaces an older one.
5. **Freeze:** from Wed 25 Nov only bug fixes are deployed (feature freeze in the team plan).

## Rollback
- **Automatic:** ECS rolls back a service by itself if the new version fails its `/health` check
  (deployment circuit breaker, set in Terraform).
- **Old images must still exist.** ECR keeps every image under its commit tag. Its cleanup rule
  (lifecycle policy, in Terraform by Hamda + Fatma) keeps the **last 20 images of each service** and
  deletes only older ones, so there is always something to roll back to.
- **Manual (one click):** GitHub → Actions → *Deploy* → *Run workflow* → tick **rollback**. The
  pipeline finds the version production ran before (each production job is named
  `Production (<commit>)`), waits for the usual approval, and redeploys those images; nothing is
  rebuilt. To deploy any other version, enter its commit instead.
- **Models** are separate: Majed's model registry keeps the previous live version and switches back
  (Student 8 acceptance test). A code rollback does not change the live model.
- After any rollback: open a `bug` issue with what failed and link the run.

## Secrets
- Real secrets (database passwords, API keys) live **only in AWS Secrets Manager**
  and reach the services as ECS environment secrets. Never in Git, `.env`, Terraform variables,
  `.tfvars`, logs, issues or chat.
- **Not secrets:** the Cognito user pool ID, app client ID, issuer and keys URL are public by design
  (the portal's browser sees them; `docs/decisions/0006`). They come from Terraform outputs, not the code.
- `.env.example` contains only fake values ending in `-local-only`. `.env` and Terraform state are in
  `.gitignore`.
- A leaked secret is rotated first, then removed (see `SECURITY_CHECKS.md`). Gitleaks checks every
  pull request.

## Least privilege (with Hamda + Fatma; `infrastructure/modules/iam`)
- One IAM role per service; each gets only the buckets, queues and secrets it uses (e.g. the dataset
  service: the datasets bucket; the scheduler: the training queue).
- The GitHub deploy role can push to ECR and update ECS services. Nothing else: it cannot create or
  delete infrastructure (that is Terraform's job, run by Hamda + Fatma).
- Workflows get `permissions: contents: read` unless a step needs more, and then only that job.
- Only the gateway and the portal are reachable from the internet; every other service only from
  inside the VPC.
