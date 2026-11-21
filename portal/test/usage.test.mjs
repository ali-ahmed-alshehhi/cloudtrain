import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  STAGES,
  USAGE_STATES,
  describeJobUsage,
  describeProjectTotal,
  formatGpuHours,
  formatUsd,
  jobUsage,
  loadProjectUsage,
  makeJobsApi,
  projectUsage,
  usageMessage,
} from "../lib/usage/cost.mjs";
import { FIXTURE_PROJECT_JOBS, fixtureJob } from "./fixtures/jobs.fixture.mjs";

const contract = readFileSync(new URL("../../contracts/openapi/job-service.yaml", import.meta.url), "utf8");

test("fixture jobs have exactly the contract's required Job fields", () => {
  const line = contract.match(/required: \[(job_id, project_id, status, spec[^\]]*)\]/);
  assert.ok(line, "found the Job schema's required list");
  const required = line[1].split(",").map((s) => s.trim()).sort();
  for (const job of FIXTURE_PROJECT_JOBS) assert.deepEqual(Object.keys(job).sort(), required, job.job_id);
});

test("jobUsage: stage from status and start; numbers kept as they are, null stays null", () => {
  const [done, , running, queued, unknown, cpu] = FIXTURE_PROJECT_JOBS.map(jobUsage);
  assert.equal(done.stage, STAGES.FINISHED);
  assert.equal(running.stage, STAGES.RUNNING);
  assert.equal(queued.stage, STAGES.NOT_STARTED);
  assert.equal(unknown.cost, null);
  assert.equal(unknown.costKnown, false);
  assert.equal(cpu.cost, 0);
  assert.equal(cpu.costKnown, true, "0 is a real price (free), not unknown");
  const cancelledEarly = jobUsage(fixtureJob(9, { status: "CANCELLED", started_at: null, gpu_hours: 0, estimated_cost_usd: 0 }));
  assert.equal(cancelledEarly.stage, STAGES.NEVER_RAN);
  const retrying = jobUsage(fixtureJob(10, { status: "QUEUED", attempt: 2, started_at: null, gpu_hours: 0.3 }));
  assert.equal(retrying.stage, STAGES.RUNNING, "a retry waiting in the queue already used machine time");
});

test("project total: sums GPU-hours, never counts an unknown price as 0, flags running jobs", () => {
  const total = projectUsage(FIXTURE_PROJECT_JOBS);
  assert.equal(total.jobs, 6);
  assert.equal(total.gpuHours, 0.5 + 4 + 0.25 + 0 + 8 + 0);
  assert.equal(Number(total.knownCost.toFixed(4)), Number((0.263 + 3.912 + 0.1315 + 0 + 0).toFixed(4)));
  assert.equal(total.unknownCostJobs, 1);
  assert.equal(total.running, 1);
  assert.deepEqual(total.rows.map((r) => r.jobId), ["job-6", "job-5", "job-4", "job-3", "job-2", "job-1"], "newest first");
  assert.deepEqual(describeProjectTotal(total), {
    gpuHours: "12.75 so far",
    cost: "at least $4.31 (1 job with unknown price) so far",
  });
});

test("project total without unknowns or running jobs is plain", () => {
  const total = projectUsage([FIXTURE_PROJECT_JOBS[0], FIXTURE_PROJECT_JOBS[1]]);
  assert.deepEqual(describeProjectTotal(total), { gpuHours: "4.50", cost: "$4.18" });
  assert.deepEqual(describeProjectTotal(projectUsage([])), { gpuHours: "0", cost: "$0.00" });
});

test("job wording for each stage", () => {
  const words = FIXTURE_PROJECT_JOBS.map((j) => describeJobUsage(jobUsage(j)));
  assert.deepEqual(words[0], { gpuHours: "0.500", cost: "$0.26", note: null });
  assert.equal(words[1].note, "Includes all 2 attempts.");
  assert.deepEqual(words[2], {
    gpuHours: "0.250 so far",
    cost: "$0.13 so far",
    note: "Still running: the numbers grow until it finishes.",
  });
  assert.equal(words[3].note, "No machine time yet: the job has not started.");
  assert.equal(words[3].cost, "—", "not started is not shown as $0.00");
  assert.equal(words[4].cost, "Price unknown");
  assert.match(words[4].note, /p5\.48xlarge/);
  assert.deepEqual(words[5], { gpuHours: "0 (CPU only)", cost: "$0.00", note: null });
});

test("formatting", () => {
  assert.equal(formatUsd(null), "Price unknown");
  assert.equal(formatUsd(0), "$0.00");
  assert.equal(formatUsd(0.004), "< $0.01");
  assert.equal(formatUsd(1234.5), "$1,234.50");
  assert.equal(formatGpuHours(0.0412), "0.041");
  assert.equal(formatGpuHours(0.004), "< 0.01");
  assert.equal(formatGpuHours(2.5), "2.50");
  assert.equal(formatGpuHours(120.25), "120.3");
  assert.equal(formatGpuHours(null), "—");
});

test("makeJobsApi calls only the gateway's /api/v1/jobs", async () => {
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push([url, options.headers.Authorization]);
    return { status: 200, json: async () => ({ items: [] }) };
  };
  const api = makeJobsApi({ gatewayUrl: "http://localhost:5810/", authToken: "t0k", fetchImpl });
  await api.listJobs("project-01");
  await api.getJob("job-7");
  assert.deepEqual(calls, [
    ["http://localhost:5810/api/v1/jobs?project_id=project-01", "Bearer t0k"],
    ["http://localhost:5810/api/v1/jobs/job-7", "Bearer t0k"],
  ]);
});

test("loadProjectUsage: states, other projects' jobs dropped, bad ids never sent", async () => {
  const answer = (status, body) => ({ listJobs: async () => ({ status, body }) });
  const stray = fixtureJob(99, { project_id: "project-02", gpu_hours: 100 });
  const ready = await loadProjectUsage({ api: answer(200, { items: [...FIXTURE_PROJECT_JOBS, stray] }), projectId: "project-01" });
  assert.equal(ready.state, USAGE_STATES.READY);
  assert.equal(ready.usage.jobs, 6);
  assert.equal(usageMessage(ready), null);
  const empty = await loadProjectUsage({ api: answer(200, { items: [] }), projectId: "project-01" });
  assert.match(usageMessage(empty).text, /No jobs/);
  for (const [status, state] of [[401, "unauthorized"], [403, "forbidden"], [404, "not_found"], [503, "unavailable"], [500, "error"]]) {
    assert.equal((await loadProjectUsage({ api: answer(status, null), projectId: "project-01" })).state, state);
  }
  const down = { listJobs: async () => { throw new TypeError("fetch failed"); } };
  assert.equal((await loadProjectUsage({ api: down, projectId: "project-01" })).state, USAGE_STATES.UNAVAILABLE);
  let called = false;
  const spy = { listJobs: async () => ((called = true), { status: 200, body: { items: [] } }) };
  assert.equal((await loadProjectUsage({ api: spy, projectId: "project-1' or 1=1" })).state, USAGE_STATES.ERROR);
  assert.equal(called, false);
  assert.match(usageMessage(null).text, /Loading/);
});
