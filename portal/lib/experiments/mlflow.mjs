// MLflow results for one job (owner: Adel, Student 10 split 2).
//
// Reads MLflow ONLY through the gateway's experiments route (gateway/app/routes.yaml):
//   /api/v1/experiments/*  ->  mlflow:5000/api/2.0/mlflow/*   (GET, and POST only on .../search)
// The gateway turns MLflow errors into the shared error format {error: {code, message, request_id}}.
//
// How a job is found (Abdullah's training worker, training/app/tracking.py):
//   - every ATTEMPT of a job is one MLflow run in experiment "cloudtrain" (MLFLOW_EXPERIMENT_NAME)
//   - tags: job_id, project_id, strategy ("single" | "ddp"), world_size, model, dataset_id, ...
//   - metrics per epoch (step = epoch): train_loss, validation_loss, accuracy, f1
//   - at the end: final_train_loss, final_validation_loss, final_accuracy, final_f1
//
// Plain JavaScript with no React, so it can be tested with `node --test`.

import { identityOf } from "../identity.mjs";

export const DEFAULT_EXPERIMENT = "cloudtrain";

/**
 * Whose results these are: job + project + experiment + API client (a new login = a new client).
 * JobResults shows only results loaded for the current identity.
 */
export function resultsIdentity({ job, api, experimentName = DEFAULT_EXPERIMENT }) {
  return identityOf(job?.job_id, job?.project_id, experimentName, api);
}

// The metrics we know, in the order they are shown. accuracy and f1 are fractions (0..1).
export const KNOWN_METRICS = Object.freeze([
  { key: "accuracy", label: "Accuracy", kind: "fraction", better: "higher" },
  { key: "f1", label: "F1 score (macro)", kind: "fraction", better: "higher" },
  { key: "validation_loss", label: "Validation loss", kind: "loss", better: "lower" },
  { key: "train_loss", label: "Training loss", kind: "loss", better: "lower" },
]);

// Charts drawn from the per-epoch history.
export const CHART_METRICS = Object.freeze(["accuracy", "validation_loss", "train_loss"]);

export const RESULT_STATES = Object.freeze({
  READY: "ready", // at least one run found
  NONE: "none", // no run for this job (yet)
  UNAUTHORIZED: "unauthorized", // 401
  FORBIDDEN: "forbidden", // 403
  UNAVAILABLE: "unavailable", // 502/503/504 or no network
  ERROR: "error", // anything else
});

const JOB_ID = /^job-[0-9]+$/;
const PROJECT_ID = /^project-[0-9]+$/;

/**
 * The three MLflow calls the results need, through the gateway.
 * Each resolves to { status, body } for every HTTP answer and rejects only when the network is down.
 * Hilal's shared gateway client can replace this later with the same shape.
 */
export function makeExperimentsApi({ gatewayUrl, authToken = "", fetchImpl = globalThis.fetch }) {
  const base = `${String(gatewayUrl).replace(/\/+$/, "")}/api/v1/experiments`;
  const headers = authToken ? { Authorization: `Bearer ${authToken}` } : {};

  async function call(path, { query, body } = {}) {
    const url = `${base}${path}${query ? `?${new URLSearchParams(query)}` : ""}`;
    const answer = await fetchImpl(url, {
      method: body ? "POST" : "GET",
      headers: body ? { ...headers, "Content-Type": "application/json" } : headers,
      body: body ? JSON.stringify(body) : undefined,
      cache: "no-store",
    });
    let parsed = null;
    try {
      parsed = await answer.json();
    } catch {
      parsed = null;
    }
    return { status: answer.status, body: parsed };
  }

  return {
    getExperimentByName: (name) => call("/experiments/get-by-name", { query: { experiment_name: name } }),
    searchRuns: (request) => call("/runs/search", { body: request }),
    getMetricHistory: (runId, key) =>
      call("/metrics/get-history", { query: { run_id: runId, metric_key: key, max_results: "1000" } }),
  };
}

function failure(answer) {
  const error = answer?.body?.error ?? null;
  if (!answer) return { state: RESULT_STATES.UNAVAILABLE, error };
  if (answer.status === 401) return { state: RESULT_STATES.UNAUTHORIZED, error };
  if (answer.status === 403) return { state: RESULT_STATES.FORBIDDEN, error };
  if ([502, 503, 504].includes(answer.status)) return { state: RESULT_STATES.UNAVAILABLE, error };
  return { state: RESULT_STATES.ERROR, error };
}

function emptyResult(state, error = null) {
  return { state, runs: [], latest: null, error };
}

/**
 * Find every MLflow run (attempt) of one job, newest first.
 * Returns { state, runs: [normalized run], latest: run|null, error }.
 */
export async function loadJobResults({ api, job, experimentName = DEFAULT_EXPERIMENT }) {
  // The ids go into an MLflow filter string, so only accept the contract's exact shapes.
  if (!JOB_ID.test(job?.job_id ?? "") || !PROJECT_ID.test(job?.project_id ?? "")) {
    return emptyResult(RESULT_STATES.ERROR, { code: "BAD_JOB", message: "This job has no valid job_id/project_id" });
  }
  try {
    const experiment = await api.getExperimentByName(experimentName);
    if (experiment.status === 404 || experiment.body?.error?.code === "RESOURCE_DOES_NOT_EXIST") {
      return emptyResult(RESULT_STATES.NONE); // no job has ever logged a run
    }
    if (experiment.status !== 200) return { ...emptyResult(), ...failure(experiment) };
    const experimentId = experiment.body?.experiment?.experiment_id;
    if (!experimentId) {
      return emptyResult(RESULT_STATES.ERROR, { code: "BAD_ANSWER", message: "MLflow sent no experiment id" });
    }

    const search = await api.searchRuns({
      experiment_ids: [experimentId],
      filter: `tags.job_id = '${job.job_id}' and tags.project_id = '${job.project_id}'`,
      order_by: ["attributes.start_time DESC"],
      max_results: 20,
    });
    if (search.status !== 200) return { ...emptyResult(), ...failure(search) };

    const raw = Array.isArray(search.body?.runs) ? search.body.runs : [];
    const runs = raw
      .map(normalizeRun)
      // Belt and braces: never show another job's or project's run, even if the filter was ignored.
      .filter((run) => run.tags.job_id === job.job_id && run.tags.project_id === job.project_id)
      .sort((a, b) => (b.startTime ?? 0) - (a.startTime ?? 0));
    runs.forEach((run, index) => {
      run.attempt = runs.length - index; // oldest run = attempt 1
    });
    if (runs.length === 0) return emptyResult(RESULT_STATES.NONE);
    return { state: RESULT_STATES.READY, runs, latest: runs[0], error: null };
  } catch {
    return emptyResult(RESULT_STATES.UNAVAILABLE); // network down
  }
}

function toNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function pairs(list) {
  const out = {};
  for (const item of Array.isArray(list) ? list : []) if (item?.key) out[item.key] = item.value;
  return out;
}

/** One MLflow run (REST answer) in a flat shape. Missing values stay null, never 0. */
export function normalizeRun(run) {
  const info = run?.info ?? {};
  const data = run?.data ?? {};
  const metrics = {};
  for (const m of Array.isArray(data.metrics) ? data.metrics : []) {
    if (!m?.key) continue;
    // MLflow sends NaN/Infinity as strings; keep them visible as text instead of dropping them.
    const value = typeof m.value === "number" ? m.value : Number(m.value);
    metrics[m.key] = { value, step: toNumber(m.step) };
  }
  const tags = pairs(data.tags);
  const startTime = toNumber(info.start_time);
  const endTime = toNumber(info.end_time);
  return {
    runId: info.run_id ?? info.run_uuid ?? null,
    runName: info.run_name ?? tags["mlflow.runName"] ?? null,
    status: info.status ?? null, // RUNNING | SCHEDULED | FINISHED | FAILED | KILLED
    startTime,
    endTime,
    durationSeconds: startTime !== null && endTime !== null && endTime >= startTime ? (endTime - startTime) / 1000 : null,
    strategy: tags.strategy ?? null,
    worldSize: toNumber(tags.world_size),
    metrics,
    params: pairs(data.params),
    tags,
    attempt: null,
  };
}

/**
 * Rows for the results table: the known metrics first, then any other metric MLflow has.
 * A final_* value wins; otherwise the latest per-epoch value is shown with its epoch.
 * A metric MLflow does not have is left out (never shown as 0).
 */
export function summarizeMetrics(run) {
  const metrics = run?.metrics ?? {};
  const rows = [];
  const used = new Set();
  for (const known of KNOWN_METRICS) {
    const final = metrics[`final_${known.key}`];
    const latest = metrics[known.key];
    used.add(`final_${known.key}`);
    used.add(known.key);
    if (final) rows.push({ ...known, value: final.value, final: true, step: latest?.step ?? null });
    else if (latest) rows.push({ ...known, value: latest.value, final: false, step: latest.step });
  }
  for (const [key, metric] of Object.entries(metrics).sort(([a], [b]) => a.localeCompare(b))) {
    if (used.has(key)) continue;
    rows.push({ key, label: key, kind: "number", better: null, value: metric.value, final: key.startsWith("final_"), step: metric.step });
  }
  return rows;
}

/** Per-epoch history of some metrics: { key: [{ step, value }] (by step) | null when it failed }. */
export async function loadMetricHistory({ api, runId, keys = CHART_METRICS }) {
  const entries = await Promise.all(
    keys.map(async (key) => {
      try {
        const answer = await api.getMetricHistory(runId, key);
        if (answer.status !== 200) return [key, null];
        const points = (Array.isArray(answer.body?.metrics) ? answer.body.metrics : [])
          .map((m) => ({ step: toNumber(m.step), value: typeof m.value === "number" ? m.value : Number(m.value) }))
          .filter((p) => p.step !== null)
          .sort((a, b) => a.step - b.step);
        return [key, points];
      } catch {
        return [key, null];
      }
    }),
  );
  return Object.fromEntries(entries);
}

/** 0.9134 -> "91.3%" for fractions, 4 significant digits otherwise; NaN stays visible. */
export function formatMetric(value, kind) {
  if (typeof value !== "number" || Number.isNaN(value)) return "NaN (not a number)";
  if (!Number.isFinite(value)) return value > 0 ? "∞" : "−∞";
  if (kind === "fraction") return `${(value * 100).toFixed(1)}%`;
  return Number(value.toPrecision(4)).toString();
}

/** 3725 -> "1 h 02 min", 200 -> "3 min 20 s", null -> null. */
export function formatDuration(seconds) {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return null;
  const s = Math.round(seconds);
  if (s < 60) return `${s} s`;
  if (s < 3600) return `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, "0")} s`;
  return `${Math.floor(s / 3600)} h ${String(Math.floor((s % 3600) / 60)).padStart(2, "0")} min`;
}

/** "single GPU", "DDP on 2 GPUs", or null when the run has no such tags. */
export function describeParallelism(run) {
  if (!run?.strategy) return null;
  const gpus = run.worldSize ? `${run.worldSize} GPU${run.worldSize === 1 ? "" : "s"}` : null;
  if (run.strategy === "single") return gpus ? `single process, ${gpus}` : "single process";
  if (run.strategy === "ddp") return gpus ? `DDP on ${gpus}` : "DDP";
  return gpus ? `${run.strategy}, ${gpus}` : run.strategy;
}

/** The message for a results state (or null when there are results to show). */
export function resultsMessage(result, jobStatus) {
  switch (result?.state) {
    case undefined:
    case null:
      return { kind: "info", text: "Loading training results…" };
    case RESULT_STATES.READY:
      return null;
    case RESULT_STATES.NONE:
      if (jobStatus === "QUEUED" || jobStatus === "SCHEDULED") {
        return { kind: "info", text: "No results yet: training has not started." };
      }
      if (jobStatus === "RUNNING") return { kind: "info", text: "No results logged yet: the first epoch is still running." };
      return { kind: "info", text: "No MLflow run was found for this job." };
    case RESULT_STATES.UNAUTHORIZED:
      return { kind: "error", text: "Please log in again to see training results." };
    case RESULT_STATES.FORBIDDEN:
      return { kind: "error", text: "You do not have access to these training results." };
    case RESULT_STATES.UNAVAILABLE:
      return { kind: "warning", text: "Training results (MLflow) are unavailable right now. Try again in a moment." };
    default:
      return {
        kind: "warning",
        text: `Could not load training results${result.error?.message ? `: ${result.error.message}` : ""}.`,
      };
  }
}
