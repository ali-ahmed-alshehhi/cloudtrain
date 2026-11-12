# Testing

**Owner:** Ali (integration), with every service owner (their own tests) and Salem (CI and security tests).

## The test layers

| Layer | What it checks | Where | Command |
|---|---|---|---|
| Lint | Code style and simple mistakes | every Python folder | `make lint` |
| Unit tests | One service's logic, without the others | `<service>/tests/` | `make test` |
| Contract tests | Each running service answers exactly as its file in `contracts/` says (Schemathesis) | `contracts/openapi/` | `make contract` |
| End-to-end | The demo walk-through through the gateway, all services running | `tests/integration/` | `make e2e` |
| Failure recovery | A worker dies mid-job; the job fails on the missing heartbeat, is retried and finishes | `tests/integration/test_failure_recovery.py` | `make e2e` |
| UI end-to-end | The whole flow in the browser | `portal/` | _(Hilal + Adel)_ |
| Security | Unauthorised access is rejected, images and dependencies scanned | `security/`, CI | _(Salem)_ |

`make check` runs lint + test + contract + e2e. Run it before every pull request; CI runs it on every
pull request and on every push to `main`.

## Rules
- Every change adds tests for the main path **and at least one failure path**.
- A walk-through step that is not delivered yet is marked `skip` with the owner's name and hand-off date;
  remove the `skip` when you deliver.

## Results
_Fill in near the end: number of tests per service, what passed, known gaps._
