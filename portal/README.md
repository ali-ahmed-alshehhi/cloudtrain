# Web Portal — `portal/`

> **In progress.** Projects and dataset upload/version selection are implemented through the gateway. Run `make check` before opening a PR. Job submission, model and prediction workflows are next.

| Owners (partners) | Port | Contracts |
|---|---|---|
| Hilal + Adel (Student 10) | **3000 (published)** | all public APIs through the gateway; `contracts/events/job-event.schema.json` |

Default framework: **Next.js** (the brief allows React or Next.js; record a change in `docs/decisions/`).
Node 24 (see `docs/decisions/0003-node-24.md`).

## What it must do
The one web interface: projects, dataset upload, job submission, job monitoring with live status and
alerts, MLflow results, the 1-GPU vs 2-GPU comparison page, models and prediction, compute usage and
cost, plus monitoring dashboards (CloudWatch / Prometheus / Grafana), end-to-end UI tests, the
performance and reliability evaluation (`docs/EVALUATION.md`) and the final demo dashboard.

**Job alerts:** the portal is the Notification service (see `docs/decisions/0002-notifications-in-portal.md`).
It calls `GET /api/v1/jobs/events?after=<last event_id>` every 5–10 seconds, with back-off.

## Endpoints
Serves web pages only. **The portal calls only the gateway** (`NEXT_PUBLIC_GATEWAY_URL`, port 5810),
never a service directly.

## Reads and writes
- Reads: every public API through the gateway.
- Monitoring reads the `job-events` queue for dashboards (the only reader of that queue).

## Acceptance test
A user completes the whole flow, from upload to deployed inference, through the web interface with
real metrics and status.


## Current implementation and ownership

Hilal owns `app/layout.js`, `app/globals.css`, `app/page.js`, the project workflow
in `app/dashboard.js`, the dataset workflow in `app/components/datasets.js`,
and the shared client in `app/lib/gateway.mjs`. Shared error rendering lives in
`app/components/problem.js`.
Adel owns the upcoming monitoring, experiment comparison, usage/cost and evaluation
features. Adel's merged `JobAlerts` and `useAlertFeed` components are integrated through
`app/components/project-alerts.js`, using the shared gateway client's `fetchEvents`
adapter. One feed runs for the selected project; remounting on project changes
prevents previous-project state from being shown. Future live job badges should
share this feed's state when the job page is built.

The project form follows `contracts/openapi/project-service.yaml`: name is required
(maximum 100 characters), description is optional (maximum 1000). A successful
create selects the returned project. The form reuses its idempotency key when an
unchanged submission is retried after an error. Loading and request errors are
shown explicitly, including the backend's request reference when available.

### Dataset workflow

Select a project to load its datasets. New dataset uploads send `project_id`,
`name`, optional `description`, `format` (`csv`, `zip` or `tar_gz`) and `file` as
multipart form data. The service validates actual file contents. A successful
upload selects the returned dataset/version. The version picker uses numbered
versions up to the backend's `latest_version`; metadata is fetched from
`GET /api/v1/datasets/{id}/versions/{version}`. There is no invented list-versions
endpoint. The details show actual file size, SHA-256 checksum, upload time and note.
Users can also upload a new version with a file and optional note.

Retries of an unchanged upload reuse the idempotency key. A new file or changed
metadata gets a new key. Switching projects resets dataset state and cancels
outstanding requests. Version fetch errors hide previous metadata and offer retry.
Clicking an already selected dataset preserves the selection and metadata.

**Backend dependency:** the current dataset service is still Faisal's in-memory
stand-in. Data disappears when that service restarts; S3/PostgreSQL persistence
and project membership enforcement remain his responsibility. Project filtering
in this UI does not replace backend authorization. Production login also remains
pending Salem's integration.

### Shared client for Adel

```js
import { createGatewayClient } from "./lib/gateway.mjs";

const api = createGatewayClient({ gatewayUrl, getToken: () => token });
const result = await api.request("/api/v1/jobs?project_id=project-01", { signal });
```

Create this client once per gateway/session (for example with React `useMemo`).
`request(path, options)` accepts `method`, `body`, `headers` and `signal`. JSON bodies
are encoded automatically; `FormData` retains its browser-generated multipart
boundary. `GatewayError` exposes `status`, `code`, `message` and `requestId`.
Abort errors remain abort errors, so components can ignore cancelled requests.
Do not put tokens in local storage or commit them. Real login integration awaits
Salem's provider; a dev token is supplied to the browser only when both
`ENVIRONMENT=local` and `AUTH_MODE=dev`. No production sign-in is implemented yet.

## Run and verify

From the repository root, with Docker Desktop running:

```bash
make up
```

Open http://localhost:3000. Create a project with a name and optional description;
it should appear in Your projects and become selected. Refresh the project list;
the project should remain. Select another project to switch its alert feed.
Check an empty name is rejected. With the gateway unavailable, refresh should
show an error rather than claiming there are no projects.

With Node 24 installed:

```bash
cd portal
npm ci
npm test
npm run build
```

Without host Node, from the repository root:

```bash
docker build --progress=plain -f portal/Dockerfile.test .
docker build -t cloudtrain-portal-hilal:projects ./portal
```

For browser integration tests, first start the local stack, then from `portal/`:

```bash
npm ci
npx playwright install chromium
npm run test:e2e
```

Alternatively, set `PLAYWRIGHT_CHROME_EXECUTABLE` to your installed Chrome
executable. These tests create small test projects and datasets in the local
backend. They cover project creation/refresh, blank-name validation, network
recovery, CSV/ZIP/TAR.GZ uploads, invalid CSV rejection, a lost upload response and
safe retry, new versions, old-version checksums, version-service errors and retry,
project switching, unauthenticated API rejection, and mobile width. Error cases
that simulate a broken network/service use browser interception; the successful
uploads and reads use the real gateway and service. Screenshots are written to
`portal/test-results/` (ignored by Git).

The test image runs both portal test suites during its build. Use the repository
root as its build context so the shared contracts are included at `/workspace/contracts`.
The production image checks the complete Next.js compilation. Before a PR, run
`make check` at the repository root and reference the actual issue as `Closes #N`.

### Verification on 16 November 2026

- All 39 portal unit tests passed (Adel's 24 alert tests plus 15 gateway/client tests).
- Two Chrome browser integration scenarios passed against the live local gateway and services.
- CSV, ZIP and TAR.GZ uploads, versions 1/2, checksum selection and retry safety passed.
- Production Next.js Docker build passed; desktop and mobile screenshots reviewed.
- Full `make check` passed: lint, service tests, all contract checks and integration walkthrough.
- The integration walkthrough reports 7 passed and 8 pre-existing skips for work still
  assigned to the team; no skips were removed by this portal change.
- Rebased onto `1a97336` (merged alerts #96, Jobs #90, branding #80, Projects fix #87).

The services currently running locally include stand-ins. These checks establish
portal integration with the current repository, not completion of classmates'
production backends or AWS deployment.

### Previous backend blocker resolved

The null-character Projects failure recorded on 15 November was fixed by Ali in
PR #87 and is included in this branch. All service contract checks now pass.

The repository checks on this machine use an isolated Python 3.11.15 interpreter:

```bash
make check PYTHON=/private/tmp/cloudtrain-python/cpython-3.11.15-macos-aarch64-none/bin/python3.11
```

Classmates with Python 3.11 on PATH can use the normal `make check` command.
The portal's JavaScript tests and browser tests must also be run explicitly with
`npm test` and `npm run test:e2e`; the root Makefile currently runs Python checks.

### Brand assets

`public/brand/cloudtrain-logo-dark.png` and `app/icon.svg` are unchanged copies
of the team's assets in `docs/brand/` (PR #80). The portal image copies `public/`
so the approved wordmark is served in production as well as development.
