# Web Portal — `portal/`

> **Stand-in.** Hilal + Adel: Replace this stand-in with your real service. Keep the contract. Run `make check` before opening a PR.
>
> What the stand-in already does, and what it does not, is written at `app/page.js`. It shows the gateway's `/health`, your project list and the job alert feed.

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
