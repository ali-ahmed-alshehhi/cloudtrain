import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  RESULT_STATES,
  describeParallelism,
  formatDuration,
  formatMetric,
  loadJobResults,
  loadMetricHistory,
  makeExperimentsApi,
  normalizeRun,
  resultsMessage,
  summarizeMetrics,
} from "../lib/experiments/mlflow.mjs";
import {
  FIXTURE_EXPERIMENT,
  FIXTURE_HISTORY,
  FIXTURE_TWO_ATTEMPTS,
  fixtureGatewayError,
  fixtureRun,
} from "./fixtures/mlflow.fixture.mjs";

const job = { job_id: "job-104", project_id: "project-01", status: "SUCCEEDED" };

// A fake API: each method answers from a prepared value (or a function of its arguments).
function fakeApi({ experiment = { status: 200, body: FIXTURE_EXPERIMENT }, search, history } = {}) {
  const calls = [];
  const answer = (value, ...args) => (typeof value === "function" ? value(...args) : value);
  return {
    calls,
    getExperimentByName: async (name) => (calls.push(["experiment", name]), answer(experiment, name)),
    searchRuns: async (request) => (calls.push(["search", request]), answer(search, request)),
    getMetricHistory: async (runId, key) => (calls.push(["history", runId, key]), answer(history, runId, key)),
  };
}

test("API calls go only to the gateway's /api/v1/experiments route, POST only on /search", async () => {
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({ url, method: options.method, body: options.body, auth: options.headers.Authorization });
    return { status: 200, json: async () => ({}) };
  };
  const api = makeExperimentsApi({ gatewayUrl: "http://localhost:5810/", authToken: "t0k", fetchImpl });
  await api.getExperimentByName("cloudtrain");
  await api.searchRuns({ experiment_ids: ["1"] });
  await api.getMetricHistory("run-1", "accuracy");
  assert.deepEqual(
    calls.map((c) => [c.method, c.url]),
    [
      ["GET", "http://localhost:5810/api/v1/experiments/experiments/get-by-name?experiment_name=cloudtrain"],
      ["POST", "http://localhost:5810/api/v1/experiments/runs/search"],
      ["GET", "http://localhost:5810/api/v1/experiments/metrics/get-history?run_id=run-1&metric_key=accuracy&max_results=1000"],
    ],
  );
  assert.ok(calls.every((c) => c.auth === "Bearer t0k"));
  // The gateway allows POST only when the path ends with /search (gateway/app/routes.yaml).
  const routes = readFileSync(new URL("../../gateway/app/routes.yaml", import.meta.url), "utf8");
  assert.match(routes, /post_allowed_when_path_ends_with: \/search/);
  assert.ok(calls.filter((c) => c.method === "POST").every((c) => c.url.endsWith("/search")));
});

test("finds the job's runs by job_id AND project_id tags, newest first, numbered as attempts", async () => {
  const api = fakeApi({ search: { status: 200, body: { runs: [...FIXTURE_TWO_ATTEMPTS].reverse() } } });
  const result = await loadJobResults({ api, job });
  assert.equal(result.state, RESULT_STATES.READY);
  const [, request] = api.calls.find(([kind]) => kind === "search");
  assert.deepEqual(request.experiment_ids, ["1"]);
  assert.equal(request.filter, "tags.job_id = 'job-104' and tags.project_id = 'project-01'");
  assert.deepEqual(result.runs.map((r) => [r.runId, r.attempt]), [["run-fixture-a", 2], ["run-fixture-old", 1]]);
  assert.equal(result.latest.runId, "run-fixture-a");
});

test("a run of another job or project is never shown, even if the server sends it", async () => {
  const stray = [fixtureRun({ runId: "x", jobId: "job-999" }), fixtureRun({ runId: "y", projectId: "project-02" })];
  const api = fakeApi({ search: { status: 200, body: { runs: stray } } });
  assert.equal((await loadJobResults({ api, job })).state, RESULT_STATES.NONE);
});

test("no experiment yet (404 RESOURCE_DOES_NOT_EXIST) and no runs both mean NONE", async () => {
  const missing = { status: 404, body: fixtureGatewayError("RESOURCE_DOES_NOT_EXIST", "Experiment not found") };
  assert.equal((await loadJobResults({ api: fakeApi({ experiment: missing }), job })).state, RESULT_STATES.NONE);
  const empty = fakeApi({ search: { status: 200, body: {} } }); // MLflow omits "runs" when there are none
  assert.equal((await loadJobResults({ api: empty, job })).state, RESULT_STATES.NONE);
});

test("401, 403, 503 and network errors give their own states", async () => {
  const cases = [
    [{ status: 401, body: fixtureGatewayError("UNAUTHORIZED", "Log in") }, RESULT_STATES.UNAUTHORIZED],
    [{ status: 403, body: fixtureGatewayError("FORBIDDEN", "No") }, RESULT_STATES.FORBIDDEN],
    [{ status: 503, body: fixtureGatewayError("SERVICE_UNAVAILABLE", "mlflow is down") }, RESULT_STATES.UNAVAILABLE],
    [{ status: 400, body: fixtureGatewayError("INVALID_PARAMETER_VALUE", "Bad filter") }, RESULT_STATES.ERROR],
  ];
  for (const [answer, state] of cases) {
    assert.equal((await loadJobResults({ api: fakeApi({ experiment: answer }), job })).state, state);
    assert.equal((await loadJobResults({ api: fakeApi({ search: answer }), job })).state, state);
  }
  const down = fakeApi({
    experiment: () => {
      throw new TypeError("fetch failed");
    },
  });
  assert.equal((await loadJobResults({ api: down, job })).state, RESULT_STATES.UNAVAILABLE);
});

test("ids that are not the contract's shape never reach the MLflow filter", async () => {
  const api = fakeApi();
  const result = await loadJobResults({ api, job: { job_id: "job-1' or '1'='1", project_id: "project-01" } });
  assert.equal(result.state, RESULT_STATES.ERROR);
  assert.equal(api.calls.length, 0);
});

test("normalizeRun: duration from start/end, GPU tags, missing values stay null (not 0)", () => {
  const run = normalizeRun(fixtureRun({ strategy: "ddp", worldSize: 2 }));
  assert.equal(run.durationSeconds, 200);
  assert.equal(run.worldSize, 2);
  assert.equal(describeParallelism(run), "DDP, 2 processes");
  const running = normalizeRun(fixtureRun({ status: "RUNNING", end: null, metrics: [] }));
  assert.equal(running.durationSeconds, null);
  assert.deepEqual(running.metrics, {});
  assert.equal(normalizeRun({}).worldSize, null);
  assert.equal(describeParallelism(normalizeRun(fixtureRun())), "single process");
});

test("summarizeMetrics: final values win; per-epoch value otherwise; unknown metrics kept; missing ones omitted", () => {
  const finished = summarizeMetrics(normalizeRun(fixtureRun()));
  assert.deepEqual(
    finished.map((r) => [r.key, r.value, r.final]),
    [["accuracy", 0.912, true], ["f1", 0.905, true], ["validation_loss", 0.2841, true], ["train_loss", 0.2512, true]],
  );
  const failed = summarizeMetrics(normalizeRun(FIXTURE_TWO_ATTEMPTS[1]));
  assert.deepEqual(failed.map((r) => [r.key, r.final, r.step]), [["accuracy", false, 1], ["train_loss", false, 1]]);
  const extra = summarizeMetrics(normalizeRun(fixtureRun({ metrics: [{ key: "epoch_seconds", value: 12.5, step: 1 }] })));
  assert.deepEqual(extra.map((r) => r.label), ["epoch_seconds"]);
});

test("loadMetricHistory: points sorted by epoch; a failed metric is null, not empty", async () => {
  const api = fakeApi({
    history: (runId, key) =>
      key === "train_loss"
        ? { status: 503, body: fixtureGatewayError("SERVICE_UNAVAILABLE", "down") }
        : { status: 200, body: { metrics: [...FIXTURE_HISTORY[key]].reverse() } },
  });
  const history = await loadMetricHistory({ api, runId: "run-fixture-a" });
  assert.deepEqual(history.accuracy.map((p) => p.step), [1, 2, 3]);
  assert.equal(history.validation_loss.at(-1).value, 0.2841);
  assert.equal(history.train_loss, null);
});

test("formatting: percentages, 4 significant digits, NaN visible, durations", () => {
  assert.equal(formatMetric(0.9134, "fraction"), "91.3%");
  assert.equal(formatMetric(0.284123, "loss"), "0.2841");
  assert.equal(formatMetric(Number.NaN, "loss"), "NaN (not a number)");
  assert.equal(formatMetric(0, "loss"), "0", "a real zero is still shown");
  assert.equal(formatDuration(200), "3 min 20 s");
  assert.equal(formatDuration(3725), "1 h 02 min");
  assert.equal(formatDuration(null), null);
});

test("resultsMessage depends on the job's status when there are no runs", () => {
  const none = { state: RESULT_STATES.NONE };
  assert.match(resultsMessage(none, "QUEUED").text, /not started/);
  assert.match(resultsMessage(none, "RUNNING").text, /first epoch/);
  assert.match(resultsMessage(none, "SUCCEEDED").text, /No MLflow run/);
  assert.equal(resultsMessage({ state: RESULT_STATES.READY }), null);
  assert.match(resultsMessage(null).text, /Loading/);
  assert.match(resultsMessage({ state: RESULT_STATES.UNAVAILABLE }).text, /unavailable/);
  assert.match(resultsMessage({ state: RESULT_STATES.ERROR, error: { message: "Bad filter" } }).text, /Bad filter/);
});
