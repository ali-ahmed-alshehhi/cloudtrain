# Deployment policy: environments, approval, rollback, secrets

Owner: Salem (Student 9). Draft for Checkpoint 1; the AWS parts start when Hamda + Fatma have ECR
and ECS ready (Wed 18 and Sun 22 Nov). Changes to this file: pull request reviewed by Ali.

## Environments
| Environment | Where | How code gets there | Who can deploy | Data |
|---|---|---|---|---|
| **local** | each laptop, `docker compose` | `make up` | anyone | fake values from `.env.example`, `AUTH_MODE=dev` |
| **CI** | GitHub Actions, thrown away after each run | every pull request and push | automatic | fake values |
| **staging** | AWS (Terraform `environments/staging`) | **automatically** after a merge to `main` passes CI and the security checks | the pipeline only | test data, real login (`AUTH_MODE=jwt`) |
| **production** (the demo) | AWS | **promotion** of an image already tested on staging, after **approval** | the pipeline only, after a reviewer approves | demo data, real login |

> **Open question for Hamda + Fatma:** Terraform has `dev` and `staging` folders. Proposal: `dev` is
> your playground for trying Terraform changes, `staging` receives every merge, and the demo runs on
> a `prod` copy of `staging` for the last week only (cost). Alternative: promote inside one
> environment. To agree before Sat 21 Nov.

## Rules
1. **Nobody deploys from a laptop** to staging or production. Only the pipeline does, with a GitHub
   OIDC role: GitHub stores **no AWS keys**.
2. **Build once, deploy the same image.** Each image is tagged with the Git commit (e.g.
   `gateway:4999c59`). Production receives exactly the image that passed on staging. Never `latest`.
3. **Only `main` can deploy.** Branches and pull requests are tested, never deployed.
4. **Approval:** the GitHub environment `production` requires one approval from **Ali or Salem**
   (not the person who merged). The deploy waits on the run page until someone clicks *Approve*.
5. **Freeze:** from Wed 25 Nov only bug fixes are deployed (feature freeze in the team plan).

## Rollback
- **Automatic:** ECS rolls back a service by itself if the new version fails its `/health` check
  (deployment circuit breaker, set in Terraform).
- **Old images must still exist.** ECR keeps every image under its commit tag. Its cleanup rule
  (lifecycle policy, in Terraform by Hamda + Fatma) keeps the **last 20 images of each service** and
  deletes only older ones, so there is always something to roll back to.
- **Manual (one click):** GitHub → Actions → *Deploy* → *Run workflow* → choose the environment and
  the last good commit. The pipeline redeploys those images; nothing is rebuilt.
- **Models** are separate: Majed's model registry keeps the previous live version and switches back
  (Student 8 acceptance test). A code rollback does not change the live model.
- After any rollback: open a `bug` issue with what failed and link the run.

## Secrets
- Real secrets (database passwords, Cognito settings, API keys) live **only in AWS Secrets Manager**
  and reach the services as ECS environment secrets. Never in Git, `.env`, Terraform variables,
  `.tfvars`, logs, issues or chat.
- `.env.example` contains only fake values ending in `-local-only`. `.env` and Terraform state are in
  `.gitignore`.
- A leaked secret is rotated first, then removed (see `SECURITY_CHECKS.md`). Gitleaks checks every
  pull request.

## Least privilege (with Hamda + Fatma, from Thu 19 Nov)
- One IAM role per service; each gets only the buckets, queues and secrets it uses (e.g. the dataset
  service: the datasets bucket; the scheduler: the training queue).
- The GitHub deploy role can push to ECR and update ECS services. Nothing else: it cannot create or
  delete infrastructure (that is Terraform's job, run by Hamda + Fatma).
- Workflows get `permissions: contents: read` unless a step needs more, and then only that job.
- Only the gateway and the portal are reachable from the internet; every other service only from
  inside the VPC.
