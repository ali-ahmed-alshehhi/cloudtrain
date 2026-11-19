// GPU-hours and estimated cost, per job and per project (owner: Adel, Student 10 split 2).
//
// The numbers come ONLY from Training Jobs (GET /api/v1/jobs and /api/v1/jobs/{id}, through the gateway):
//   gpu_hours           number, summed over every attempt (a running attempt counts up to "now")
//   estimated_cost_usd  number, or null = price unknown (machine type missing from contracts/pricing.yaml, #108/#114)
// The portal never prices anything itself: it only adds up a project's jobs and words the result.
// "Estimated": hourly on-demand price x machine time. Not a bill (decision 0011: no real AWS account).
//
// Plain JavaScript with no React, so it can be tested with `node --test`.

const TERMINAL = new Set(["SUCCEEDED", "FAILED", "CANCELLED"]);

export const COST_NOTE = "Estimate: on-demand hourly price × machine time, from contracts/pricing.yaml. Not a bill.";

export const STAGES = Object.freeze({
  NOT_STARTED: "not_started", // no machine time yet
  RUNNING: "running", // the meter is still going: numbers are "so far"
  FINISHED: "finished", // final numbers
  NEVER_RAN: "never_ran", // cancelled (or failed) before any attempt started
});

function toNumber(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** How many GPUs the job asked for (spec.resources.gpu_count), or null if the spec does not say. */
export function requestedGpus(job) {
  return toNumber(job?.spec?.resources?.gpu_count);
}

/** The usage of one job, in a flat shape. Missing values stay null; nothing is invented. */
export function jobUsage(job) {
  const status = job?.status ?? null;
  const gpuHours = toNumber(job?.gpu_hours);
  const cost = toNumber(job?.estimated_cost_usd);
  const started = Boolean(job?.started_at) || (gpuHours ?? 0) > 0;
  let stage;
  if (TERMINAL.has(status)) stage = started ? STAGES.FINISHED : STAGES.NEVER_RAN;
  else stage = started ? STAGES.RUNNING : STAGES.NOT_STARTED;
  return {
    jobId: job?.job_id ?? null,
    status,
    stage,
    gpuHours,
    cost, // null = price unknown (or no answer)
    costKnown: cost !== null,
    machineType: job?.machine_type ?? null,
    gpus: requestedGpus(job),
    attempt: toNumber(job?.attempt),
    createdAt: job?.created_at ?? null,
  };
}

/**
 * The total of a project's jobs.
 * - gpuHours: sum of every job's GPU-hours (always known)
 * - knownCost: sum of the jobs whose cost is known; unknownCostJobs: how many are not (never counted as 0)
 * - running: how many jobs are still running, so the totals are "so far"
 */
export function projectUsage(jobs) {
  const rows = (Array.isArray(jobs) ? jobs : []).map(jobUsage);
  rows.sort((a, b) => String(b.createdAt ?? "").localeCompare(String(a.createdAt ?? "")));
  let gpuHours = 0;
  let knownCost = 0;
  let unknownCostJobs = 0;
  let running = 0;
  for (const row of rows) {
    gpuHours += row.gpuHours ?? 0;
    if (row.costKnown) knownCost += row.cost;
    else if (row.stage !== STAGES.NOT_STARTED && row.stage !== STAGES.NEVER_RAN) unknownCostJobs += 1;
    if (row.stage === STAGES.RUNNING) running += 1;
  }
  return { rows, jobs: rows.length, gpuHours, knownCost, unknownCostJobs, running };
}

/** "$1.33", "$0.00" (free), "< $0.01", or "Price unknown" for null. */
export function formatUsd(value) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "Price unknown";
  if (value > 0 && value < 0.01) return "< $0.01";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value);
}

/** 0.0412 -> "0.041", 2.5 -> "2.50", 120.25 -> "120.3", null -> "—". */
export function formatGpuHours(value) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  if (value === 0) return "0";
  if (value < 0.01) return "< 0.01";
  if (value < 1) return value.toFixed(3);
  if (value < 100) return value.toFixed(2);
  return value.toFixed(1);
}

/** Words for one job's usage: { gpuHours, cost, note } ready to show. */
export function describeJobUsage(usage) {
  const cpuOnly = usage.gpus === 0;
  const hours = cpuOnly ? "0 (CPU only)" : formatGpuHours(usage.gpuHours);
  switch (usage.stage) {
    case STAGES.NOT_STARTED:
      return { gpuHours: "—", cost: "—", note: "No machine time yet: the job has not started." };
    case STAGES.NEVER_RAN:
      return { gpuHours: "0", cost: formatUsd(0), note: "Stopped before it started: no machine time was used." };
    case STAGES.RUNNING:
      return {
        gpuHours: `${hours} so far`,
        cost: usage.costKnown ? `${formatUsd(usage.cost)} so far` : "Price unknown",
        note: usage.costKnown
          ? "Still running: the numbers grow until it finishes."
          : `No price for ${usage.machineType ?? "this machine type"} in the price list, so the cost is unknown.`,
      };
    default:
      return {
        gpuHours: hours,
        cost: formatUsd(usage.cost),
        note: usage.costKnown
          ? usage.attempt > 1
            ? `Includes all ${usage.attempt} attempts.`
            : null
          : `No price for ${usage.machineType ?? "this machine type"} in the price list, so the cost is unknown.`,
      };
  }
}

/** The project total in words: "$4.21", "$4.21 so far", "at least $4.21 (1 job with unknown price)". */
export function describeProjectTotal(total) {
  let cost = formatUsd(total.knownCost);
  if (total.unknownCostJobs > 0) {
    const jobs = total.unknownCostJobs === 1 ? "1 job" : `${total.unknownCostJobs} jobs`;
    cost = `at least ${cost} (${jobs} with unknown price)`;
  }
  if (total.running > 0) cost += " so far";
  return { gpuHours: formatGpuHours(total.gpuHours) + (total.running > 0 ? " so far" : ""), cost };
}

/** GET /api/v1/jobs?project_id=… and GET /api/v1/jobs/{id} through the gateway. Same shape as the other helpers. */
export function makeJobsApi({ gatewayUrl, authToken = "", fetchImpl = globalThis.fetch }) {
  const base = `${String(gatewayUrl).replace(/\/+$/, "")}/api/v1/jobs`;
  const headers = authToken ? { Authorization: `Bearer ${authToken}` } : {};
  async function call(url) {
    const answer = await fetchImpl(url, { headers, cache: "no-store" });
    let body = null;
    try {
      body = await answer.json();
    } catch {
      body = null;
    }
    return { status: answer.status, body };
  }
  return {
    listJobs: (projectId) => call(`${base}?${new URLSearchParams({ project_id: projectId })}`),
    getJob: (jobId) => call(`${base}/${encodeURIComponent(jobId)}`),
  };
}

export const USAGE_STATES = Object.freeze({
  READY: "ready",
  UNAUTHORIZED: "unauthorized",
  FORBIDDEN: "forbidden",
  NOT_FOUND: "not_found",
  UNAVAILABLE: "unavailable",
  ERROR: "error",
});

const PROJECT_ID = /^project-[0-9]+$/;

/** Load a project's jobs and total them. Returns { state, usage, error }. */
export async function loadProjectUsage({ api, projectId }) {
  if (!PROJECT_ID.test(projectId ?? "")) {
    return { state: USAGE_STATES.ERROR, usage: null, error: { message: "Not a valid project id" } };
  }
  let answer;
  try {
    answer = await api.listJobs(projectId);
  } catch {
    return { state: USAGE_STATES.UNAVAILABLE, usage: null, error: null };
  }
  const error = answer?.body?.error ?? null;
  if (answer.status === 200) {
    const items = Array.isArray(answer.body?.items) ? answer.body.items : null;
    if (!items) return { state: USAGE_STATES.ERROR, usage: null, error: { message: "Unexpected answer" } };
    // Belt and braces: only this project's jobs count towards its total.
    return { state: USAGE_STATES.READY, usage: projectUsage(items.filter((j) => j?.project_id === projectId)), error: null };
  }
  if (answer.status === 401) return { state: USAGE_STATES.UNAUTHORIZED, usage: null, error };
  if (answer.status === 403) return { state: USAGE_STATES.FORBIDDEN, usage: null, error };
  if (answer.status === 404) return { state: USAGE_STATES.NOT_FOUND, usage: null, error };
  if ([502, 503, 504].includes(answer.status)) return { state: USAGE_STATES.UNAVAILABLE, usage: null, error };
  return { state: USAGE_STATES.ERROR, usage: null, error };
}

/** The message for a usage state, or null when there is a table to show. */
export function usageMessage(result) {
  switch (result?.state) {
    case undefined:
    case null:
      return { kind: "info", text: "Loading usage and cost…" };
    case USAGE_STATES.READY:
      return result.usage.jobs === 0 ? { kind: "info", text: "No jobs in this project yet, so no usage." } : null;
    case USAGE_STATES.UNAUTHORIZED:
      return { kind: "error", text: "Please log in again to see usage and cost." };
    case USAGE_STATES.FORBIDDEN:
      return { kind: "error", text: "You are not a member of this project, so its usage is hidden." };
    case USAGE_STATES.NOT_FOUND:
      return { kind: "error", text: "This project was not found." };
    case USAGE_STATES.UNAVAILABLE:
      return { kind: "warning", text: "Usage is unavailable right now (Training Jobs did not answer). Try again in a moment." };
    default:
      return { kind: "warning", text: `Could not load usage${result.error?.message ? `: ${result.error.message}` : ""}.` };
  }
}
