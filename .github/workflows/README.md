# CI/CD workflows — `.github/workflows/`

| Owner | Approval |
|---|---|
| Salem (Student 9) | Ali (CODEOWNERS covers all of `.github/`) |

## What it must do
- `ci.yml` — starter CI by Ali: lint and unit tests for changed folders, Docker builds, compose up,
  `make contract`, `make e2e`, logs on failure. **Salem extends it** with image scanning, dependency
  checks, security tests, the staging deploy and the approval to promote.
- `assign-reviewers.yml` — requests the right reviewer on each pull request (from `team.yml`).

Port: — · Endpoints: none (these run on GitHub, not in docker-compose).

## Acceptance test
A code change triggers tests and builds, deploys to staging, is promoted through approval, and
unauthorised access is rejected.
