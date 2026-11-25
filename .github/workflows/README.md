# CI/CD workflows — `.github/workflows/`

| Owner | Approval |
|---|---|
| Salem (Student 9) | Ali (CODEOWNERS covers all of `.github/`) |

## From a code change to production
```
pull request ──► CI  + Security  (+ Login, + Terraform when their folders change)   all must be green
                          │ merge to main
                          ▼
                 Images: build the 10 images, Trivy gate, push  <service>:<commit>
                          │ automatic
                          ▼
                 Deploy ─► Staging: deploy that commit + smoke test of those exact images
                          │ waits for Ali or Salem to click "Approve"
                          ▼
                          Production: the same images, nothing rebuilt
Rollback: Actions → Deploy → Run workflow → tick "rollback" (also needs the approval)
```

| Workflow | When | What it does | Blocks the merge or the deploy when |
|---|---|---|---|
| `ci.yml` (Ali, extended by Salem) | every pull request, every push to `main` | 1. ruff + pytest of changed services, shared code and contract tests · 2. Docker build · 3. start everything (`make up`) · 4. contract tests · 5. demo walk-through (`make e2e`), including the failure-recovery test (a worker killed mid-job is retried) · logs on failure | any step fails |
| `security.yml` | every pull request, every push to `main`, Mondays 09:17 Abu Dhabi, on demand | 1. **Gitleaks**: secrets in the code or its history · 2. **pip-audit / npm audit**: libraries with known holes · 3. **Trivy**: holes inside every image · 4. **Checkov**: risky Terraform settings | a secret; a vulnerable library; a CRITICAL image hole that has a fix; a risky cloud setting. How to fix: [`security/SECURITY_CHECKS.md`](../../security/SECURITY_CHECKS.md) |
| `login.yml` | pull requests touching login, gateway, projects or Cognito; every push to `main`; on demand | starts the AWS Emulator, creates the Cognito pool, groups and test users, runs CloudTrain with `AUTH_MODE=jwt`: 10 login tests (`security/tests`) + the demo walk-through with real tokens | a request without a valid login is NOT refused, or a real login does not work |
| `terraform.yml` | pull requests touching `infrastructure/`, pushes to `main`, on demand | `terraform fmt` + `validate`, then applies the whole dev environment on the AWS Emulator, checks its outputs and destroys it | the Terraform does not format, validate or apply |
| `images.yml` | every push to `main` (and pull requests that change it) | builds the 10 images, refuses any with a CRITICAL hole that has a fix, pushes each tagged with its commit: `ghcr.io/ali-ahmed-alshehhi/cloudtrain/<service>:<commit>` (ECR once there is an AWS account) | an image fails the Trivy gate |
| `deploy.yml` + [`../deploy/deploy.sh`](../deploy/deploy.sh) | automatically after `images.yml` succeeds on `main`; by hand (a commit, or rollback) | **Which version** → **Staging**: each ECS service gets a new task-definition revision with only the image changed, then a smoke test runs those images with `make e2e` → **Production**: the same, after approval | staging smoke test fails; production waits until a reviewer approves |
| `assign-reviewers.yml` | a pull request is opened | asks the right teammate to review (`team.yml`, `scripts/pick_reviewers.py`) | — |

## Rules every workflow follows
- **Least privilege:** `permissions: contents: read`; a job gets more only for its own step
  (e.g. `packages: write` to push images).
- **No stored cloud keys:** images push with the run's own short-lived token; with an AWS account
  the deploy signs in with GitHub OIDC (role `github_deploy`, `infrastructure/modules/iam`).
- **Third-party actions pinned** to a release or a commit (Gitleaks to its commit).
- **Only `main` deploys.** Pull requests are tested, never deployed (a pull request that changes
  `deploy.yml` runs the staging job on its own throw-away emulator, never production).
- **Build once, deploy the same image**, tagged by commit, never `latest`.
- **Approval:** the GitHub environment `production` has required reviewers **Ali and Salem**; one
  approval is enough. Staging and production each have their own queue, so a production deploy
  waiting for approval never holds back the staging deploys of newer commits.

## Where to look
- Each run writes a summary table on its page (Actions → the run).
- Waiting for approval: Actions → Deploy → the run shows **Review deployments**.
- Policy (environments, approval, rollback, secrets): [`security/DEPLOYMENT_POLICY.md`](../../security/DEPLOYMENT_POLICY.md).
- Step by step for operators: [`docs/DEPLOYMENT_GUIDE.md`](../../docs/DEPLOYMENT_GUIDE.md), section 4.

Port: — · Endpoints: none (these run on GitHub, not in docker-compose).

## Acceptance test
A code change triggers tests and builds, deploys to staging, is promoted through approval, and
unauthorised access is rejected.

| Part | Shown by |
|---|---|
| code change → tests and builds | `ci.yml`, `security.yml`, `images.yml` on the merge commit |
| → staging | `deploy.yml` job *Staging (<commit>)*, smoke test green |
| → production only after approval | job *Production (<commit>)* waits on **Review deployments** |
| unauthorised access is rejected | `login.yml`: no token, a changed token, a forged key, an unsigned token, another app's token and an access token are all refused with 401 |
