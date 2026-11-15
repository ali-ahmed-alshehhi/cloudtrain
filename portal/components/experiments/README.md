# Training results from MLflow (owner: Adel, Student 10 split 2)

Shows one job's MLflow results on Hilal's job page: final metrics, per-epoch charts, and one tab per
attempt (each retry is its own MLflow run). Reads MLflow **only through the gateway**:
`/api/v1/experiments/*` → `mlflow:5000/api/2.0/mlflow/*` (GET, plus POST on `.../search`).

| File | What it is |
|---|---|
| `../../lib/experiments/mlflow.mjs` | Find a job's runs, read metric history, format values, state messages |
| `JobResults.js` | The results box (table, charts, attempt tabs, messages) |
| `MetricChart.js` | One small per-epoch line chart, with tooltip and "show as table" |

## How runs are found
Abdullah's training worker (`training/app/tracking.py`) logs each attempt as a run in the experiment
`cloudtrain`, tagged `job_id`, `project_id`, `strategy`, `world_size`. The portal asks for
`tags.job_id = '<job>' and tags.project_id = '<project>'`. Metrics: `accuracy`, `f1`, `validation_loss`,
`train_loss` per epoch, and the same with `final_` at the end. Other metrics are shown by their name.

## How to use it on the job page (for Hilal)

```jsx
"use client";
import { useMemo } from "react";
import { makeExperimentsApi } from "../lib/experiments/mlflow.mjs";
import JobResults from "../components/experiments/JobResults";

const experimentsApi = useMemo(() => makeExperimentsApi({ gatewayUrl, authToken }), [gatewayUrl, authToken]);
<JobResults job={job} api={experimentsApi} liveStatus={liveStatus} />
```
`job` is the answer of `GET /api/v1/jobs/{id}`. `liveStatus` is optional: pass the live status from
the alert feed (`latestJobStatus(job, feedState.events).status`) so results reload when the job
finishes. While a run is RUNNING the box reloads every 30 seconds by itself.

## What it never does
- Never shows a missing metric as 0, and never invents values: missing metrics are left out.
- Never shows a run whose `job_id`/`project_id` tags do not match the job, even if MLflow returns one.
- Never puts an id that is not `job-N` / `project-N` into the MLflow filter.

## Test
`cd portal && npm test`. MLflow test answers are in `test/fixtures/mlflow.fixture.mjs`, marked **FIXTURE**.
