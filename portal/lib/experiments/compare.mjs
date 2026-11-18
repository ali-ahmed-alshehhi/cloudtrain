// 1 GPU vs multi-GPU DDP comparison (owner: Adel, Student 10 split 2).
//
// Reads the project's finished MLflow runs through the gateway (/api/v1/experiments, read only) and the
// jobs' GPU-hours and cost from Training Jobs (/api/v1/jobs/{id}). Walk-through step 8: "two finished runs
// of the same model, strategy 'single' and 'ddp', both visible in MLflow with time, throughput and
// GPU-hours to compare."
//
// The arithmetic is the SAME as Ahmed + Abdulla's benchmark tool (training/distributed/metrics.py), so the
// portal and docs/BENCHMARKS.md agree:
//   time per epoch  = mean of the epochs after the first (the first pays for warm-up), per run
//   throughput      = images in those epochs / their seconds
//   one row per GPU count = the mean of its repeated runs (seeds)
//   speedup         = time per epoch on 1 GPU / time per epoch on N GPUs; efficiency = speedup / N
//   only runs with the same workload are compared; CPU runs are left out (a functional check, not scaling)
// Time per epoch needs two per-epoch MLflow metrics (step = epoch): EPOCH_SECONDS and EPOCH_IMAGES.
// When a run does not log them, those columns say so; nothing is estimated in their place.
// GPU-hours and cost are Training Jobs' numbers (all attempts of the job), never computed here.

import { DEFAULT_EXPERIMENT, normalizeRun } from "./mlflow.mjs";

export const EPOCH_SECONDS = "epoch_seconds";
export const EPOCH_IMAGES = "epoch_images";
// The benchmark tool's SAME_WORKLOAD, with the names the training runtime logs as MLflow params.
export const SAME_WORKLOAD = Object.freeze(["model", "dataset_id", "dataset_version", "epochs", "batch_size", "num_workers"]);
export const MAX_RUNS = 50;

export const COMPARE_STATES = Object.freeze({
  READY: "ready",
  NONE: "none", // no finished run with strategy/world_size tags in this project
  UNAUTHORIZED: "unauthorized",
  FORBIDDEN: "forbidden",
  UNAVAILABLE: "unavailable",
  ERROR: "error",
});

const PROJECT_ID = /^project-[0-9]+$/;

const mean = (values) => (values.length ? values.reduce((a, b) => a + b, 0) / values.length : null);
/** The mean of a column, or null as soon as one repeat lacks the value (never a mean of a subset). */
function meanOfAll(values) {
  return values.every((v) => typeof v === "number" && Number.isFinite(v)) ? mean(values) : null;
}

/** The workload of a run: params first (the runtime logs them), tags as a fallback. undefined = not logged. */
export function workloadOf(run) {
  const workload = {};
  for (const key of SAME_WORKLOAD) workload[key] = run.params?.[key] ?? run.tags?.[key];
  return workload;
}

export function workloadKey(workload) {
  return SAME_WORKLOAD.map((key) => `${key}=${workload[key] ?? "?"}`).join("|");
}

export function workloadLabel(workload) {
  const parts = [workload.model, workload.dataset_id && `${workload.dataset_id} v${workload.dataset_version ?? "?"}`];
  if (workload.epochs) parts.push(`${workload.epochs} epochs`);
  if (workload.batch_size) parts.push(`batch ${workload.batch_size} per GPU`);
  if (workload.num_workers) parts.push(`${workload.num_workers} data workers`);
  return parts.filter(Boolean).join(" · ");
}

/**
 * Headline numbers of one run, like summarise() in training/distributed/metrics.py.
 * `seconds` and `images` are per-epoch histories [{ step, value }] (or null when not logged).
 */
export function summariseRun({ run, seconds, images }) {
  const bySteps = (points) => [...(points ?? [])].filter((p) => Number.isFinite(p.value)).sort((a, b) => a.step - b.step);
  const secs = bySteps(seconds);
  let timePerEpoch = null;
  let imagesPerSecond = null;
  if (secs.length > 0) {
    const steady = secs.length > 1 ? secs.slice(1) : secs;
    const total = steady.reduce((sum, p) => sum + p.value, 0);
    timePerEpoch = total / steady.length;
    const imagesByStep = new Map(bySteps(images).map((p) => [p.step, p.value]));
    if (total > 0 && steady.every((p) => imagesByStep.has(p.step))) {
      imagesPerSecond = steady.reduce((sum, p) => sum + imagesByStep.get(p.step), 0) / total;
    }
  }
  const accuracy = run.metrics?.final_accuracy?.value ?? run.metrics?.accuracy?.value ?? null;
  return { timePerEpoch, imagesPerSecond, totalSeconds: run.durationSeconds, accuracy };
}

/**
 * Rows of one workload group, like scaling_rows() in training/distributed/metrics.py.
 * entries: [{ run, summary, gpus, job: { gpuHours, cost } | null }]
 */
export function scalingRows(entries) {
  const byGpus = new Map();
  for (const entry of entries) {
    if (!byGpus.has(entry.gpus)) byGpus.set(entry.gpus, []);
    byGpus.get(entry.gpus).push(entry);
  }
  const baselineRuns = byGpus.get(1) ?? [];
  const baseline = meanOfAll(baselineRuns.map((e) => e.summary.timePerEpoch));
  const rows = [...byGpus.entries()]
    .sort(([a], [b]) => a - b)
    .map(([gpus, runs]) => {
      const timePerEpoch = meanOfAll(runs.map((e) => e.summary.timePerEpoch));
      const speedup = baseline !== null && timePerEpoch ? baseline / timePerEpoch : null;
      return {
        gpus,
        strategy: gpus === 1 ? "single" : "ddp",
        repeats: runs.length,
        runIds: runs.map((e) => e.run.runId),
        timePerEpoch,
        imagesPerSecond: meanOfAll(runs.map((e) => e.summary.imagesPerSecond)),
        totalSeconds: meanOfAll(runs.map((e) => e.summary.totalSeconds)),
        accuracy: meanOfAll(runs.map((e) => e.summary.accuracy)),
        speedup,
        efficiency: speedup === null ? null : speedup / gpus,
        gpuHours: meanOfAll(runs.map((e) => e.job?.gpuHours ?? null)),
        cost: meanOfAll(runs.map((e) => e.job?.cost ?? null)),
      };
    });
  const problems = [];
  if (!byGpus.has(1)) problems.push("No 1-GPU run of this workload yet: speedup needs one as the baseline.");
  if (byGpus.size === 1) problems.push("Only one GPU count so far: run the same job with another GPU count to compare.");
  if (rows.some((r) => r.timePerEpoch === null)) {
    problems.push(
      `Time per epoch and throughput need the per-epoch MLflow metrics "${EPOCH_SECONDS}" and "${EPOCH_IMAGES}", which these runs do not log yet. Speedup is not shown without them.`,
    );
  }
  return { rows, problems };
}

/** Group runs by workload; leave out CPU runs and runs without the strategy/world_size tags. */
export function groupComparable(entries) {
  const groups = new Map();
  let leftOut = 0;
  for (const entry of entries) {
    if (!entry.run.strategy || !(entry.gpus >= 1)) {
      leftOut += 1;
      continue;
    }
    const workload = workloadOf(entry.run);
    const key = workloadKey(workload);
    if (!groups.has(key)) groups.set(key, { key, workload, label: workloadLabel(workload), entries: [] });
    groups.get(key).entries.push(entry);
  }
  const out = [...groups.values()].map((group) => ({ ...group, ...scalingRows(group.entries) }));
  // Groups that can actually be compared (two GPU counts, with a 1-GPU baseline) first.
  out.sort((a, b) => b.rows.length - a.rows.length || a.label.localeCompare(b.label));
  return { groups: out, leftOut };
}

function failure(answer) {
  const error = answer?.body?.error ?? null;
  if (answer?.status === 401) return { state: COMPARE_STATES.UNAUTHORIZED, error };
  if (answer?.status === 403) return { state: COMPARE_STATES.FORBIDDEN, error };
  if ([502, 503, 504].includes(answer?.status)) return { state: COMPARE_STATES.UNAVAILABLE, error };
  return { state: COMPARE_STATES.ERROR, error };
}

const empty = (state, error = null) => ({ state, groups: [], leftOut: 0, error });

/**
 * Load the comparison for one project.
 * experimentsApi: makeExperimentsApi(...) from ./mlflow.mjs · jobsApi: makeJobsApi(...) from ../usage/cost.mjs
 */
export async function loadComparison({ experimentsApi, jobsApi, projectId, experimentName = DEFAULT_EXPERIMENT }) {
  if (!PROJECT_ID.test(projectId ?? "")) return empty(COMPARE_STATES.ERROR, { message: "Not a valid project id" });
  try {
    const experiment = await experimentsApi.getExperimentByName(experimentName);
    if (experiment.status === 404 || experiment.body?.error?.code === "RESOURCE_DOES_NOT_EXIST") {
      return empty(COMPARE_STATES.NONE);
    }
    if (experiment.status !== 200) return { ...empty(), ...failure(experiment) };
    const search = await experimentsApi.searchRuns({
      experiment_ids: [experiment.body?.experiment?.experiment_id],
      filter: `tags.project_id = '${projectId}' and attributes.status = 'FINISHED'`,
      order_by: ["attributes.start_time DESC"],
      max_results: MAX_RUNS,
    });
    if (search.status !== 200) return { ...empty(), ...failure(search) };
    const runs = (Array.isArray(search.body?.runs) ? search.body.runs : [])
      .map(normalizeRun)
      .filter((run) => run.tags.project_id === projectId && run.status === "FINISHED");
    if (runs.length === 0) return empty(COMPARE_STATES.NONE);

    const jobs = new Map();
    const entries = await Promise.all(
      runs.map(async (run) => {
        const [seconds, images, job] = await Promise.all([
          history(experimentsApi, run.runId, EPOCH_SECONDS),
          history(experimentsApi, run.runId, EPOCH_IMAGES),
          jobOf(jobsApi, run.tags.job_id, jobs),
        ]);
        // GPUs: what the job asked for (Training Jobs); the run's world_size if the job is not readable.
        const gpus = job?.gpus ?? run.worldSize;
        return { run, summary: summariseRun({ run, seconds, images }), gpus, job };
      }),
    );
    const grouped = groupComparable(entries);
    if (grouped.groups.length === 0) return { ...empty(COMPARE_STATES.NONE), leftOut: grouped.leftOut };
    return { state: COMPARE_STATES.READY, ...grouped, error: null };
  } catch {
    return empty(COMPARE_STATES.UNAVAILABLE);
  }
}

async function history(api, runId, key) {
  try {
    const answer = await api.getMetricHistory(runId, key);
    if (answer.status !== 200) return null;
    return (Array.isArray(answer.body?.metrics) ? answer.body.metrics : []).map((m) => ({
      step: Number(m.step),
      value: typeof m.value === "number" ? m.value : Number(m.value),
    }));
  } catch {
    return null;
  }
}

async function jobOf(jobsApi, jobId, cache) {
  if (!jobsApi || !jobId) return null;
  if (!cache.has(jobId)) {
    cache.set(
      jobId,
      jobsApi
        .getJob(jobId)
        .then((answer) => {
          if (answer.status !== 200 || !answer.body) return null;
          const gpu = answer.body.spec?.resources?.gpu_count;
          return {
            gpus: Number.isInteger(gpu) ? gpu : null,
            gpuHours: Number.isFinite(answer.body.gpu_hours) ? answer.body.gpu_hours : null,
            cost: Number.isFinite(answer.body.estimated_cost_usd) ? answer.body.estimated_cost_usd : null,
            machineType: answer.body.machine_type ?? null,
          };
        })
        .catch(() => null),
    );
  }
  return cache.get(jobId);
}

export function comparisonMessage(result) {
  switch (result?.state) {
    case undefined:
    case null:
      return { kind: "info", text: "Loading the 1 GPU vs DDP comparison…" };
    case COMPARE_STATES.READY:
      return null;
    case COMPARE_STATES.NONE:
      return { kind: "info", text: "No finished training runs to compare in this project yet." };
    case COMPARE_STATES.UNAUTHORIZED:
      return { kind: "error", text: "Please log in again to see the comparison." };
    case COMPARE_STATES.FORBIDDEN:
      return { kind: "error", text: "You do not have access to this project's training runs." };
    case COMPARE_STATES.UNAVAILABLE:
      return { kind: "warning", text: "Training results (MLflow) are unavailable right now. Try again in a moment." };
    default:
      return { kind: "warning", text: `Could not load the comparison${result.error?.message ? `: ${result.error.message}` : ""}.` };
  }
}

/** "1.82×", "91%", "24,640", "2.0 s"; "not logged" for null. */
export function formatSpeedup(value) {
  return value === null ? "—" : `${value.toFixed(2)}×`;
}
export function formatEfficiency(value) {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}
export function formatThroughput(value) {
  return value === null ? "not logged" : new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value);
}
export function formatSeconds(value) {
  if (value === null) return "not logged";
  return value < 10 ? `${value.toFixed(2)} s` : `${value.toFixed(1)} s`;
}
