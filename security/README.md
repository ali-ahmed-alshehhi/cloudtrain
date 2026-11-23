# Security, login and secrets — `security/`

| Owner | Port | Contracts |
|---|---|---|
| Salem (Student 9) | — | `contracts/error-format.json` (401/403), login rules in `docs/ARCHITECTURE.md` |

Salem also owns `.github/workflows/` (CI/CD): [the pipeline from a code change to production](../.github/workflows/README.md).

## What is in place (on `main`)
| Area | What | Where |
|---|---|---|
| Login | **Amazon Cognito** user pool (no self sign-up, 12+ character passwords), portal app client, groups `admin`, `data-scientist`, `viewer`. The gateway checks every token (RS256 signature, issuer, audience, expiry, ID token only) when `AUTH_MODE=jwt` | [`docs/decisions/0006`](../docs/decisions/0006-login-provider-cognito.md), `infrastructure/modules/identity`, `gateway/app` (Ali) |
| Login tests | real Cognito tokens on the AWS Emulator against the whole system: no token, the laptop dev token, a changed token, another key, an unsigned token, another app's token and an access token → **401**; another user's project → **403** | [`tests/test_login.py`](tests/test_login.py), [`login/README.md`](login/README.md), `login.yml` |
| Automatic checks | Gitleaks (secrets), pip-audit + npm audit (libraries), Trivy (images), Checkov (Terraform) on every pull request and every Monday | [`SECURITY_CHECKS.md`](SECURITY_CHECKS.md), `security.yml` |
| Secrets | only in AWS Secrets Manager: RDS manages the master password itself; each service reads only its own database secret `cloudtrain/<env>/database/<schema>`. Nothing secret in Git, `.env.example`, Terraform variables or GitHub | [`DEPLOYMENT_POLICY.md`](DEPLOYMENT_POLICY.md) → Secrets |
| Least privilege | one IAM role per service (Hamda + Fatma); the ECS execution role pulls only our images, writes only our logs, reads only the listed secrets; the GitHub deploy role (OIDC, `main` and the two environments only) can push images and update services in its own cluster, nothing else | `infrastructure/modules/iam` |
| Deploy rules | staging automatic, production only after approval by Ali or Salem, one-click rollback to the previous version, images kept per commit (last 20) | [`DEPLOYMENT_POLICY.md`](DEPLOYMENT_POLICY.md), `deploy.yml` |

## Known limits (because we use the AWS Emulator, decision 0011)
- The emulator's ECR does not accept image uploads, so images live on GitHub Container Registry;
  with an AWS account the same workflow pushes to ECR.
- ECS services run no tasks on the emulator (`ecs_desired_count = 0`): a deploy changes the ECS
  service records, and the smoke test proves the same images work by running them with Compose.
- The load balancer listens on HTTP; a real deployment adds an HTTPS certificate (ACM).
- Security groups are created but not enforced by the emulator.
- Roles (`cognito:groups`) are in every token; today the services check ownership (a user only
  sees their projects). A "viewer cannot submit a job" rule is the next step if roles are enforced.

## Documents in this folder
- [`SECURITY_CHECKS.md`](SECURITY_CHECKS.md) — the four automatic checks, what to do when one fails,
  exceptions, and the security tests.
- [`DEPLOYMENT_POLICY.md`](DEPLOYMENT_POLICY.md) — environments, approval, rollback, secrets and
  least privilege.
- [`login/README.md`](login/README.md) — run the real login on a laptop.

## Endpoints
None of its own. Real login lives in the gateway behind `AUTH_MODE=jwt`.

## Reads and writes
Policies, scripts and security test notes in this folder. **Never** a real secret or key.

## Acceptance test
A code change triggers tests and builds, deploys to staging, is promoted through approval, and
unauthorised access is rejected. How each part is shown: [`.github/workflows/README.md`](../.github/workflows/README.md#acceptance-test).
