# Security checks

Owner: Salem (Student 9). Workflow: [`.github/workflows/security.yml`](../.github/workflows/security.yml).

They run on every pull request, on every push to `main`, every Monday morning, and on demand
(GitHub → Actions → Security → Run workflow).

| # | Check | Tool | What it catches | Fails the run when |
|---|---|---|---|---|
| 1 | Secrets | Gitleaks | A password, token or key in the code or anywhere in Git history | any finding |
| 2 | Dependencies | pip-audit, npm audit | A Python or portal library with a published vulnerability | any Python finding; a portal finding rated high or critical |
| 3 | Docker images | Trivy | Vulnerabilities in the operating system and libraries inside each image we build | a CRITICAL vulnerability that already has a fix (HIGH ones are listed, not blocking) |
| 4 | Terraform | Checkov | Risky cloud settings: public buckets, missing encryption, open security groups | any failed check (the skip list is agreed with Hamda + Fatma before this check becomes required) |

## When a check fails on your pull request
1. Open the failed job on the pull request's **Checks** tab. The log says what was found and where.
2. **Secret found:** do not just delete the line, because the old commit still contains it. Tell
   Salem and Ali straight away, then **rotate** the secret (create a new one, disable the old one).
   Only after that remove it from the code.
3. **Library or image vulnerability:** upgrade to the fixed version the log shows (in
   `requirements.txt`, `package.json`, or the `FROM` line of the Dockerfile), then push again.
4. **Terraform finding:** fix the setting. If it is a deliberate choice, add a skip comment on that
   resource with the reason (`# checkov:skip=CKV_AWS_XX: reason`) and ask Salem to review.
5. **No fix exists yet / false alarm:** ask Salem. An exception is recorded here, with a reason and
   an end date, never silently.

## Exceptions
| Check | Finding | Reason | Until | Agreed by |
|---|---|---|---|---|
| — | none yet | | | |

## Security tests (unauthorised access is rejected)
| Test | Expected | Where | Status |
|---|---|---|---|
| No `Authorization` header | 401 `NOT_AUTHENTICATED` | `gateway/tests/test_gateway.py` | ✅ exists (Ali) |
| Wrong or malformed token | 401 | `gateway/tests/test_gateway.py` | ✅ exists (Ali) |
| Expired or wrongly signed JWT | 401 | gateway, `AUTH_MODE=jwt` | to add with the real login (Fri 20 Nov) |
| User opens another user's project or dataset | 403 | project and dataset services | after Ali's and Faisal's membership checks |
| Role without permission (e.g. viewer submits a job) | 403 | gateway or job service | after roles exist (Cognito groups) |
| Only the gateway (5810) and portal (3000) are reachable | other ports closed | `docker-compose.yml`, AWS security groups | to add (Checkpoint 3) |
