# CI/CD workflows — `.github/workflows/`

| Owner | Approval |
|---|---|
| Salem (Student 9) | Ali (CODEOWNERS covers all of `.github/`) |

## What it must do
- `ci.yml` — starter CI by Ali: lint and unit tests for changed folders, Docker builds, compose up,
  `make contract`, `make e2e`, logs on failure. **Salem extends it** with image scanning, dependency
  checks, security tests, the staging deploy and the approval to promote.

### What CI checks for each part (Checkpoint 1)
| Part | Lint | Unit tests | Docker build | Runs in compose + contract + end-to-end |
|---|---|---|---|---|
| gateway, project-service, dataset-service, job-service, scheduler, training, model-registry, inference-service | ruff, when the folder changes | pytest, when the folder changes | when the folder changes | every run |
| portal (Node) | — (its owners add a lint script) | — | when the folder changes | every run |
| mlflow | — | — | when the folder changes | every run |
| shared code: `tests/`, `scripts/` | ruff, every run | contract-file and script tests, every run | — | — |

A change to a shared file (`contracts/`, `local/`, `scripts/`, `tests/`, `docker-compose.yml`,
`Makefile`, `.env.example`) checks and builds everything. Each run writes a short summary table on
its GitHub Actions page.

- `assign-reviewers.yml` — requests the right reviewer on each pull request (from `team.yml`).

Port: — · Endpoints: none (these run on GitHub, not in docker-compose).

## Acceptance test
A code change triggers tests and builds, deploys to staging, is promoted through approval, and
unauthorised access is rejected.
