import { test } from "node:test";
import assert from "node:assert/strict";
import { JOB_DEFAULTS, jobSubmission, retryKey, canCancel, newestJob, jobRecord } from "../lib/jobs/form.mjs";
const spec = (changes = {}, version = 2) => jobSubmission("project-01", "dataset-07", version, { ...JOB_DEFAULTS, ...changes });
test("job form preserves the exact dataset version and contract types", () => {
  const job = spec(); assert.equal(job.dataset_version, 2); assert.equal(job.hyperparameters.epochs, 1); assert.equal(job.hyperparameters.learning_rate, 0.05); assert.equal(job.hyperparameters.hidden_size, 8); assert.deepEqual(job.parallelism, { strategy: "single", world_size: 1 }); assert.equal(job.resources.gpu_count, 0); assert.ok(!("job_id" in job));
});
test("DDP derives world size from GPU count, with a minimum of two", () => {
  assert.deepEqual(spec({ strategy: "ddp", gpu_count: "2" }).parallelism, { strategy: "ddp", world_size: 2 });
  for (const gpu_count of ["0", "1"]) assert.throws(() => spec({ strategy: "ddp", gpu_count }), /at least 2/);
});
test("invalid numeric limits and nested/overriding extras are rejected before submission", () => {
  for (const change of [{ epochs: "" }, { epochs: "1.5" }, { gpu_count: "9" }, { learning_rate: "0" }, { learning_rate: "NaN" }, { retry_limit: "6" }, { extras: '[]' }, { extras: '{"foo":null}' }, { extras: '{"foo":{}}' }, { extras: '{"epochs":5}' }]) assert.throws(() => spec(change));
  assert.throws(() => spec({}, 0));
});
test("retry keys survive lost responses/navigation for unchanged forms and change for changed specs", () => {
  const values = new Map(); const storage = { getItem: (k) => values.get(k), setItem: (k, v) => values.set(k, v) };
  assert.equal(retryKey(spec(), storage, () => "one"), "one");
  assert.equal(retryKey(spec(), storage, () => "two"), "one");
  assert.equal(retryKey(spec({}, 1), storage, () => "two"), "two");
  assert.equal(retryKey(spec(), storage, () => "three"), "one");
  assert.equal(retryKey(spec(), { getItem() { throw Error(); }, setItem() { throw Error(); } }, () => "fallback"), "fallback");
});
test("only active jobs may be cancelled", () => {
  for (const s of ["QUEUED", "SCHEDULED", "RUNNING"]) assert.equal(canCancel(s), true);
  for (const s of ["SUCCEEDED", "FAILED", "CANCELLED"]) assert.equal(canCancel(s), false);
});

test("late pre-cancel reads cannot resurrect a cancelled job", () => {
  const current = { job_id: "job-1", project_id: "project-01", status: "CANCELLED", attempt: 1, updated_at: "2026-11-23T12:00:02Z" };
  assert.equal(newestJob(current, { ...current, status: "RUNNING", updated_at: "2026-11-23T12:00:01Z" }), current);
  assert.equal(newestJob(current, { ...current, status: "RUNNING" }), current);
  assert.equal(newestJob(current, { ...current, job_id: "job-2" }), current);
});

test("a malformed or wrong-identity successful job response fails safely", () => {
  const good = { job_id: "job-1", project_id: "project-01", status: "QUEUED", spec: {}, history: [] };
  assert.equal(jobRecord(good, "job-1"), good);
  for (const bad of [null, { ...good, spec: null }, { ...good, history: null }, { ...good, status: "UNKNOWN" }, { ...good, job_id: "job-2" }]) assert.throws(() => jobRecord(bad, "job-1"));
  assert.throws(() => jobRecord(good, "job-1", "project-02"));
});
