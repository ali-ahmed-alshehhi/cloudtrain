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

## Switching jobs
Switching `job_id`, `project_id`, experiment or API client (a new login) shows "Loading…" at once:
the box is keyed by that identity, and every stored answer carries the identity it was loaded for and
is shown only while it is still current (`lib/identity.mjs`, tested in `test/identity.test.mjs`).
A late answer for the previous job is never shown under the new one.

## What it never does
- Never shows a missing metric as 0, and never invents values: missing metrics are left out.
- Never shows a run whose `job_id`/`project_id` tags do not match the job, even if MLflow returns one.
- Never puts an id that is not `job-N` / `project-N` into the MLflow filter.

## Test
`cd portal && npm test`. MLflow test answers are in `test/fixtures/mlflow.fixture.mjs`, marked **FIXTURE**.

## 1 GPU vs multi-GPU DDP comparison (`RunComparison.js`, `../../lib/experiments/compare.mjs`)
Walk-through step 8: finished MLflow runs of the same workload with strategy `single` and `ddp`, side by side.

```jsx
import { makeExperimentsApi } from "../lib/experiments/mlflow.mjs";
import { makeJobsApi } from "../lib/usage/cost.mjs";
import RunComparison from "../components/experiments/RunComparison";

<RunComparison projectId={projectId} experimentsApi={experimentsApi} jobsApi={jobsApi} />
```

- **Same arithmetic as `docs/BENCHMARKS.md`** (`training/distributed/metrics.py`): time per epoch leaves out the
  first epoch; one row per GPU count = mean of its runs; speedup = 1-GPU time ÷ N-GPU time; efficiency = speedup ÷ N.
  Checked against the Python tool on the same input: identical numbers.
- **Same workload only** (model, dataset and version, epochs, batch size, data workers, from the run's MLflow params);
  CPU runs and runs without `strategy`/`world_size` tags are left out.
- **GPU-hours and cost** are Training Jobs' numbers for each run's job (`job_id` tag), never computed here.
- **Needs two per-epoch MLflow metrics** (step = epoch): `epoch_seconds` and `epoch_images`, the same per-epoch
  `seconds` and `images` the benchmark tool records. Until the training runtime logs them, those columns say
  "not logged" and no speedup is shown.
- **Where it ran** comes from the run's MLflow tag `result_label`, set by whoever ran it (Ahmed + Abdulla, agreed on
  #76), e.g. `2 processes on CPU, local stack` or `measured on Kaggle 2x T4, not on AWS`. A run without it shows
  "not labelled" and a note says not to read it as GPU or cloud numbers; runs from different places are flagged, so
  the speedup is not read as like for like.
