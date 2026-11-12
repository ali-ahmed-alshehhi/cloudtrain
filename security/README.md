# Security, login and secrets — `security/`

| Owner | Port | Contracts |
|---|---|---|
| Salem (Student 9) | — | `contracts/error-format.json` (401/403), login rules in `docs/ARCHITECTURE.md` |

Salem also owns `.github/workflows/` (CI/CD).

## What it must do
- Login and permissions: set up the login provider (default **Cognito**, or another OIDC provider;
  record a change in `docs/decisions/`) and plug real JWT checking into the gateway's one auth
  function, with Ali.
- Secrets in AWS Secrets Manager; least-privilege IAM, with Hamda + Fatma.
- Image scanning and dependency checks in CI.
- Environment deployment rules, approval and rollback procedures.
- Security testing across services (e.g. unauthorised access is rejected).

## Endpoints
None of its own. Real login lives in the gateway behind `AUTH_MODE=jwt`.

## Reads and writes
Policies, scripts and security test notes in this folder. **Never** a real secret or key.

## Acceptance test
A code change triggers tests and builds, deploys to staging, is promoted through approval, and
unauthorised access is rejected.
