import assert from "node:assert/strict";
import { test } from "node:test";

import {
  COMPARE_STATES,
  EPOCH_IMAGES,
  EPOCH_SECONDS,
  RESULT_LABEL,
  comparisonMessage,
  formatEfficiency,
  formatSeconds,
  formatSpeedup,
  formatThroughput,
  groupComparable,
  loadComparison,
  summariseRun,
} from "../lib/experiments/compare.mjs";
import { normalizeRun } from "../lib/experiments/mlflow.mjs";
import { FIXTURE_COMPARISON, comparisonRun, history } from "./fixtures/comparison.fixture.mjs";
import { FIXTURE_EXPERIMENT, fixtureGatewayError } from "./fixtures/mlflow.fixture.mjs";
import { fixtureJob } from "./fixtures/jobs.fixture.mjs";

const close = (actual, expected, digits = 6) => assert.equal(Number(actual.toFixed(digits)), Number(expected.toFixed(digits)));

// Fake gateway: MLflow answers from the fixture, Training Jobs answers per job.
function apis({ runs = FIXTURE_COMPARISON.runs, seconds = FIXTURE_COMPARISON.seconds, images = FIXTURE_COMPARISON.images,
  jobs = FIXTURE_COMPARISON.jobs, experiment = { status: 200, body: FIXTURE_EXPERIMENT }, search } = {}) {
  const calls = [];
  const experimentsApi = {
    getExperimentByName: async () => experiment,
    searchRuns: async (request) => (calls.push(request), search ?? { status: 200, body: { runs } }),
    getMetricHistory: async (runId, key) => {
      if (key === EPOCH_SECONDS && seconds[runId]) return { status: 200, body: history(key, seconds[runId]) };
      if (key === EPOCH_IMAGES && seconds[runId] && images) return { status: 200, body: history(key, images) };
      return { status: 200, body: {} }; // MLflow omits "metrics" when a metric was never logged
    },
  };
  const jobsApi = {
    getJob: async (jobId) => {
      const j = jobs[jobId];
      if (!j) return { status: 404, body: fixtureGatewayError("NOT_FOUND", "no") };
      return { status: 200, body: fixtureJob(Number(jobId.split("-")[1]), {
        gpu_hours: j.gpu_hours, estimated_cost_usd: j.cost, resources: { gpu_count: j.gpus } }) };
    },
  };
  return { experimentsApi, jobsApi, calls };
}

test("summariseRun follows the benchmark tool: the first epoch is left out, throughput from the same epochs", () => {
  const run = normalizeRun(FIXTURE_COMPARISON.runs[0]);
  const s = summariseRun({ run, seconds: history("s", [3.0, 2.0, 2.0]).metrics, images: history("i", [50000, 50000, 50000]).metrics });
  assert.equal(s.timePerEpoch, 2.0);
  assert.equal(s.imagesPerSecond, 25000);
  assert.equal(s.totalSeconds, 30);
  assert.equal(s.accuracy, 0.74);
  const one = summariseRun({ run, seconds: history("s", [4.0]).metrics, images: null });
  assert.equal(one.timePerEpoch, 4.0, "a single epoch is used as it is");
  assert.equal(one.imagesPerSecond, null, "no images logged: no throughput");
  const none = summariseRun({ run, seconds: null, images: null });
  assert.deepEqual([none.timePerEpoch, none.imagesPerSecond], [null, null]);
});

test("1 GPU vs 2 GPUs: mean of repeats, speedup and efficiency against the 1-GPU mean", async () => {
  const { experimentsApi, jobsApi, calls } = apis();
  const result = await loadComparison({ experimentsApi, jobsApi, projectId: "project-01" });
  assert.equal(result.state, COMPARE_STATES.READY);
  assert.equal(calls[0].filter, "tags.project_id = 'project-01' and attributes.status = 'FINISHED'");
  assert.equal(result.groups.length, 1);
  const [group] = result.groups;
  assert.equal(group.label, "resnet18 · dataset-1 v1 · 3 epochs · batch 128 per GPU");
  assert.deepEqual(group.problems, []);
  const [one, two] = group.rows;
  assert.deepEqual([one.gpus, one.strategy, one.repeats, two.gpus, two.strategy, two.repeats], [1, "single", 2, 2, "ddp", 2]);
  close(one.timePerEpoch, 2.0);
  close(two.timePerEpoch, 1.25);
  close(two.speedup, 1.6);
  close(two.efficiency, 0.8);
  close(one.speedup, 1);
  close(two.imagesPerSecond, (50000 / 1.25 + 50000 / 1.25) / 2);
  close(one.totalSeconds, 31);
  close(two.accuracy, 0.74);
  close(two.gpuHours, (0.0111 + 0.0122) / 2, 6);
  close(two.cost, (0.0217 + 0.0239) / 2, 6);
  assert.deepEqual([one.labels, two.labels], [["FIXTURE, not a real run"], ["FIXTURE, not a real run"]]);
});

test("where a result ran comes from its result_label tag, and a missing label is said out loud", async () => {
  assert.equal(RESULT_LABEL, "result_label");
  const runs = FIXTURE_COMPARISON.runs.map((run) =>
    run.info.run_id === "r-2gpu-b" ? { ...run, data: { ...run.data, tags: run.data.tags.filter((t) => t.key !== RESULT_LABEL) } } : run,
  );
  const { experimentsApi, jobsApi } = apis({ runs });
  const [group] = (await loadComparison({ experimentsApi, jobsApi, projectId: "project-01" })).groups;
  const two = group.rows.find((r) => r.gpus === 2);
  assert.deepEqual([two.labels, two.unlabelled], [["FIXTURE, not a real run"], 1]);
  assert.match(group.problems.join(" "), /1 of 4 runs do not say where they ran \(MLflow tag "result_label"\)/);
  assert.doesNotMatch(group.problems.join(" "), /different places/);
});

test("runs from different places are flagged, so the speedup is not read as like for like", async () => {
  const placed = (run, label) => ({ ...run, data: { ...run.data, tags: run.data.tags.map((t) => (t.key === RESULT_LABEL ? { ...t, value: label } : t)) } });
  const runs = FIXTURE_COMPARISON.runs.map((run) =>
    placed(run, run.info.run_id.startsWith("r-1gpu") ? "2 processes on CPU, local stack" : "measured on Kaggle 2x T4, not on AWS"),
  );
  const { experimentsApi, jobsApi } = apis({ runs });
  const [group] = (await loadComparison({ experimentsApi, jobsApi, projectId: "project-01" })).groups;
  assert.deepEqual(group.rows.map((r) => r.labels), [["2 processes on CPU, local stack"], ["measured on Kaggle 2x T4, not on AWS"]]);
  assert.match(group.problems.join(" "), /ran in different places \(2 processes on CPU, local stack; measured on Kaggle 2x T4, not on AWS\)/);
  assert.doesNotMatch(group.problems.join(" "), /do not say where/);
});

test("runs without per-epoch timing: no speedup, a clear note, the known columns still shown", async () => {
  const { experimentsApi, jobsApi } = apis({ seconds: {} });
  const [group] = (await loadComparison({ experimentsApi, jobsApi, projectId: "project-01" })).groups;
  assert.ok(group.rows.every((r) => r.timePerEpoch === null && r.speedup === null && r.efficiency === null));
  assert.ok(group.rows.every((r) => r.totalSeconds !== null && r.gpuHours !== null));
  assert.match(group.problems.join(" "), /epoch_seconds/);
  assert.equal(formatSeconds(null), "not logged");
});

test("a mean never hides a missing repeat; an unknown price stays unknown", async () => {
  const seconds = { ...FIXTURE_COMPARISON.seconds };
  delete seconds["r-2gpu-b"]; // one DDP repeat did not log timing
  const jobs = { ...FIXTURE_COMPARISON.jobs, "job-22": { gpus: 2, gpu_hours: 0.0122, cost: null } };
  const { experimentsApi, jobsApi } = apis({ seconds, jobs });
  const [, two] = (await loadComparison({ experimentsApi, jobsApi, projectId: "project-01" })).groups[0].rows;
  assert.equal(two.timePerEpoch, null);
  assert.equal(two.speedup, null);
  assert.equal(two.cost, null, "one unknown price: no average cost");
});

test("different workloads are never compared; CPU runs and untagged runs are left out", async () => {
  const runs = [
    ...FIXTURE_COMPARISON.runs,
    comparisonRun({ runId: "r-other", jobId: "job-31", gpus: 2, batch: 256 }), // another batch size
    comparisonRun({ runId: "r-cpu", jobId: "job-41", gpus: 2 }), // world_size 2 but the job had 0 GPUs
  ];
  const untagged = comparisonRun({ runId: "r-old", jobId: "job-51", gpus: 1 });
  untagged.data.tags = untagged.data.tags.filter((t) => t.key !== "strategy");
  runs.push(untagged);
  const jobs = { ...FIXTURE_COMPARISON.jobs, "job-31": { gpus: 2, gpu_hours: 0.01, cost: 0.02 }, "job-41": { gpus: 0, gpu_hours: 0, cost: 0 } };
  const seconds = { ...FIXTURE_COMPARISON.seconds, "r-other": [2, 1, 1], "r-cpu": [9, 9, 9] };
  const { experimentsApi, jobsApi } = apis({ runs, jobs, seconds });
  const result = await loadComparison({ experimentsApi, jobsApi, projectId: "project-01" });
  assert.equal(result.leftOut, 2);
  assert.equal(result.groups.length, 2);
  assert.equal(result.groups[0].rows.length, 2, "the comparable group comes first");
  const lone = result.groups[1];
  assert.match(lone.label, /batch 256/);
  assert.match(lone.problems.join(" "), /No 1-GPU run/);
});

test("only this project's finished runs count, even if the server sends others", async () => {
  const runs = [
    ...FIXTURE_COMPARISON.runs,
    comparisonRun({ runId: "r-x", jobId: "job-61", gpus: 2, project: "project-02" }),
    comparisonRun({ runId: "r-y", jobId: "job-62", gpus: 2, status: "FAILED" }),
  ];
  const { experimentsApi, jobsApi } = apis({ runs, seconds: { ...FIXTURE_COMPARISON.seconds, "r-x": [1, 1], "r-y": [1, 1] } });
  const [group] = (await loadComparison({ experimentsApi, jobsApi, projectId: "project-01" })).groups;
  assert.deepEqual(group.rows.map((r) => r.repeats), [2, 2]);
});

test("job unreadable: GPUs from the run's world_size, GPU-hours and cost unknown", async () => {
  const { experimentsApi, jobsApi } = apis({ jobs: {} });
  const [one, two] = (await loadComparison({ experimentsApi, jobsApi, projectId: "project-01" })).groups[0].rows;
  assert.deepEqual([one.gpus, two.gpus], [1, 2]);
  assert.deepEqual([two.gpuHours, two.cost], [null, null]);
  close(two.speedup, 1.6);
});

test("states: none, 401, 403, unavailable, network down, bad id", async () => {
  const none = await loadComparison({ ...apis({ runs: [] }), projectId: "project-01" });
  assert.equal(none.state, COMPARE_STATES.NONE);
  assert.match(comparisonMessage(none).text, /No finished training runs/);
  const missing = { status: 404, body: fixtureGatewayError("RESOURCE_DOES_NOT_EXIST", "x") };
  assert.equal((await loadComparison({ ...apis({ experiment: missing }), projectId: "project-01" })).state, COMPARE_STATES.NONE);
  for (const [status, state] of [[401, "unauthorized"], [403, "forbidden"], [503, "unavailable"], [400, "error"]]) {
    const out = await loadComparison({ ...apis({ search: { status, body: fixtureGatewayError("X", "y") } }), projectId: "project-01" });
    assert.equal(out.state, state);
  }
  const down = { getExperimentByName: async () => { throw new TypeError("fetch failed"); } };
  assert.equal((await loadComparison({ experimentsApi: down, jobsApi: null, projectId: "project-01" })).state, COMPARE_STATES.UNAVAILABLE);
  const bad = apis();
  assert.equal((await loadComparison({ ...bad, projectId: "project-1' or '1'='1" })).state, COMPARE_STATES.ERROR);
  assert.equal(bad.calls.length, 0);
  assert.match(comparisonMessage(null).text, /Loading/);
});

test("formatting", () => {
  assert.equal(formatSpeedup(1.6), "1.60×");
  assert.equal(formatSpeedup(null), "—");
  assert.equal(formatEfficiency(0.8), "80%");
  assert.equal(formatThroughput(40000), "40,000");
  assert.equal(formatThroughput(null), "not logged");
  assert.equal(formatSeconds(1.25), "1.25 s");
  assert.equal(formatSeconds(31), "31.0 s");
});

test("groupComparable alone: a lone run is shown with what is missing", () => {
  const run = normalizeRun(comparisonRun({ runId: "r", jobId: "job-1", gpus: 1 }));
  const { groups } = groupComparable([{ run, summary: summariseRun({ run, seconds: null, images: null }), gpus: 1, job: null }]);
  assert.match(groups[0].problems.join(" "), /Only one GPU count/);
});
