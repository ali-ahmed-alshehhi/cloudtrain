# Usage and cost (owner: Adel, Student 10 split 2)

GPU-hours and estimated cost per job and per project. The numbers come **only** from Training Jobs through
the gateway (`GET /api/v1/jobs?project_id=…`, `GET /api/v1/jobs/{id}`): `gpu_hours` and
`estimated_cost_usd` (`contracts/openapi/job-service.yaml`). The portal never prices anything; it only adds
up a project's jobs and words the result.

| File | What it is |
|---|---|
| `../../lib/usage/cost.mjs` | Stage of a job, project totals, wording, formatting, `makeJobsApi`, `loadProjectUsage` |
| `JobCost.js` | The box for one job (job page) |
| `ProjectUsage.js` | The table and total for one project (project page) |

## How to use them (for Hilal)
```jsx
import { useMemo } from "react";
import { makeJobsApi } from "../lib/usage/cost.mjs";
import JobCost from "../components/usage/JobCost";
import ProjectUsage from "../components/usage/ProjectUsage";

<JobCost job={job} />  // job = GET /api/v1/jobs/{id}; reload it when the live status changes

const jobsApi = useMemo(() => makeJobsApi({ gatewayUrl, authToken }), [gatewayUrl, authToken]);
<ProjectUsage projectId={projectId} api={jobsApi} renderJobLink={(id) => <a href={`/jobs/${id}`}>{id}</a>} />
```

## Rules it keeps
| Situation | Shown |
|---|---|
| Not started yet | GPU-hours "—", cost "—", "No machine time yet" (not $0.00) |
| Running (or a retry waiting) | "… so far", the numbers grow; the project table reloads every 30 s |
| `estimated_cost_usd: null` | **"Price unknown"**, never $0 (#108, #114); the total says "at least $X (N jobs with unknown price)" |
| `0` on a free machine (`local-cpu`) | $0.00, "0 (CPU only)" GPU-hours |
| Retried job | the backend's numbers already cover every attempt: "Includes all N attempts" |
| Switching project or login | "Loading…" at once, never the previous project's numbers (keyed box, `lib/identity.mjs`) |

Every cost is labelled **"Estimate … Not a bill."**: hourly on-demand price × machine time, and the team
uses the AWS Emulator, not a billed account (decision 0011). The prices are in `contracts/pricing.yaml`
(real us-east-1 prices from #111; until that merges, the file's values are placeholders).

## Test
`cd portal && npm test`. Jobs in `test/fixtures/jobs.fixture.mjs` are **FIXTURE** (made up) and have
exactly the contract's required Job fields.
