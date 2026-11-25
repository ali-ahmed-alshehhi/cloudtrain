# Web Portal — `portal/`

> **In progress.** Projects and dataset upload/version selection are implemented through the gateway. Run `make check` before opening a PR. Job list, submission and detail pages now cover the CPU training workflow. Model and prediction pages remain next.

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
prevents previous-project state from being shown. The jobs list and detail page each share one project event feed between live badges and alerts.

The project form follows `contracts/openapi/project-service.yaml`: name is required
(maximum 100 characters), description is optional (maximum 1000). A successful
create selects the returned project. The form reuses its idempotency key when an
unchanged submission is retried after an error. Loading and request errors are
shown explicitly, including the backend's request reference when available.

### Comparison and usage & cost pages (Adel)

Two pages of their own, next to Hilal's projects page (which they do not change):

| Page | Walk-through step | Shows | Data (all through the gateway) |
|---|---|---|---|
| `/compare` | 8 | 1 GPU vs multi-GPU DDP runs of one project: time per epoch, throughput, speedup, efficiency, accuracy, GPU-hours, cost (`components/experiments/RunComparison.js`) | `/api/v1/experiments/*` (MLflow) and `/api/v1/jobs/{id}` |
| `/usage` | 12 | Every job of one project with machine, GPU-hours and estimated cost, and the project total (`components/usage/ProjectUsage.js`) | `/api/v1/jobs?project_id=…` |

Both use `components/pages/WorkspacePage.js`: the portal's sidebar plus a project picker
(`GET /api/v1/projects`). The chosen project is kept in the address (`/usage?project=project-04`),
so a reload or a shared link shows the same one; a project the user does not have is ignored and
the first project is shown (`lib/pages/project-choice.mjs`). GPU-hours and cost are only the
values Training Jobs returns: a missing price shows "Price unknown", never $0. CPU-only runs
(local `local-cpu` jobs) are left out of the comparison, so locally it says there is nothing
to compare until 1-GPU and DDP runs exist on the cloud stack.

The shared sidebar links to both pages. Direct links are http://localhost:3000/compare and http://localhost:3000/usage.


### Training jobs (Hilal, #58 / #59)

- `/jobs?project=project-01`: list that project's jobs, with one shared live event feed, status badges and links to each run. New project jobs/status changes trigger a list refresh through that feed; a manual refresh handles recovery.
- `/jobs/new?project=project-01`: select a dataset and its exact version. The public version endpoint supplies size/checksum before submission. Choose `tabular_mlp` for numeric CSV or `resnet18` for the supported image workload, strategy, resources, training settings and execution limits. Extra hyperparameters accept only scalar JSON values. The browser rejects invalid DDP world size/GPU counts and numeric limits before the backend's own validation.
- `/jobs/job-104`: show the authorised job, complete status history with reasons, Adel's live badge and per-job alerts, usage/cost and MLflow results. Events refresh the job snapshot and results. Transient errors have explicit retry; a denied/missing job does not display a previous job. Active jobs can be cancelled after confirmation. Late reads cannot overwrite a newer cancellation response.

Every call uses the gateway. The submission sends JSON with `Idempotency-Key`, never an invented job ID. An unchanged failed submission keeps its key in memory and, when available, `sessionStorage`, keyed by the full submission. Reloading/re-entering an identical form reuses it. Changing the dataset version/settings makes a different request. Session storage contains only form metadata/retry keys, never login tokens. Project selection and fields are disabled during submission. Navigation/reload can lose an in-flight response, so unchanged retries must use the saved key.

A small laptop smoke run: upload an 8-row CSV with numeric `radius,texture,perimeter` and target `diagnosis` containing four `B` and four `M` rows. Choose `tabular_mlp`, one epoch, batch size 4, GPU count 0 and default extras. Submit, then follow QUEUED / SCHEDULED / RUNNING / SUCCEEDED and the logged MLflow results. Real GPU/DDP performance is not claimed on the emulator.

The shared navigation now links Projects, Training jobs, Compare runs and Usage & cost. The home page's project alerts link to job details. Model promotion/prediction pages and portal real sign-in remain separate work. MLflow parallelism labels now describe processes rather than infer GPUs from world size, so laptop CPU runs are not labelled as GPU training.

`tests/e2e/jobs.test.cjs` uses clearly labelled fixture gateway responses for version choice, DDP validation, a lost POST response plus reload/safe retry, cancellation, access denial and project switching. `tests/e2e/jobs-live.test.cjs` creates a real small project/dataset, submits through the form and verifies history and MLflow through the running local gateway/worker. Its setup uses `.env`'s local token without printing it. These tests create local test records. Run with the stack healthy using `npm run test:e2e`.

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
metadata gets a new key. Project switching, creation and refresh are disabled while a dataset or version upload is in progress, so its request and retry key stay alive. Otherwise switching projects resets dataset state and cancels outstanding reads. Version fetch errors hide previous metadata and offer retry.
Clicking an already selected dataset preserves the selection and metadata.

**Backend dependency:** Faisal's persistent dataset service (#91) is now on main, including project membership enforcement. PostgreSQL records persist; uploaded files in the free local LocalStack S3 do not survive a LocalStack restart (decision 0005). Project filtering in this UI does not replace backend authorization. Salem's real-login tooling is on main; integrating sign-in into these portal pages remains pending.

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
`AUTH_MODE=dev` and `ENVIRONMENT=local` (or ENVIRONMENT omitted in an older local `.env`). Explicit nonlocal environments never receive it. No production sign-in is implemented yet.

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
Open http://localhost:3000/compare and http://localhost:3000/usage, pick a project and
reload: the same project stays selected.

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
project switching, unauthenticated API rejection, and mobile width. `pages.test.cjs`
covers the comparison and usage pages: project kept in the address and after a reload,
an unknown project ignored, and no browser request to anything but the portal and gateway. Error cases
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

### Jobs verification on 23 November 2026

91 portal unit tests pass. All 6 browser scenarios pass, including a real CPU job submitted through the form, history, MLflow results, original projects/dataset workflows and Adel's comparison/cost pages. After correcting the CPU/process label, the live CPU-job scenario passed again. The production image builds. Full `make check` passes: all service suites and contracts, integration 25 passed / 4 existing skips (short-settings recovery test, real-login step in dev mode, scheduler release and benchmark comparison). No skipped step was removed by this portal change.
