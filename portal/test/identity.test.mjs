// Regression tests for PR #98 review (Hilal): results of job-1 must never show under job-2.
import assert from "node:assert/strict";
import { test } from "node:test";

import { RESULT_STATES, loadJobResults, resultsIdentity } from "../lib/experiments/mlflow.mjs";
import { identityOf, labelled, objectIdentity, valueFor } from "../lib/identity.mjs";
import { FIXTURE_EXPERIMENT, fixtureRun } from "./fixtures/mlflow.fixture.mjs";

const job1 = { job_id: "job-1", project_id: "project-1" };
const job2 = { job_id: "job-2", project_id: "project-2" };

test("objects count by identity, not content; plain values by value", () => {
  const a = {};
  const b = {};
  assert.equal(objectIdentity(a), objectIdentity(a));
  assert.notEqual(objectIdentity(a), objectIdentity(b));
  assert.equal(objectIdentity(null), "none");
  assert.equal(identityOf("job-1", "project-1"), identityOf("job-1", "project-1"));
  assert.notEqual(identityOf("job-1", a), identityOf("job-1", b));
});

test("resultsIdentity changes with job, project, experiment and API client (new login)", () => {
  const api = {};
  const base = resultsIdentity({ job: job1, api });
  assert.equal(resultsIdentity({ job: { ...job1 }, api }), base, "same job, same client: same box");
  assert.notEqual(resultsIdentity({ job: job2, api }), base);
  assert.notEqual(resultsIdentity({ job: { ...job1, project_id: "project-2" }, api }), base);
  assert.notEqual(resultsIdentity({ job: job1, api, experimentName: "other" }), base);
  assert.notEqual(resultsIdentity({ job: job1, api: {} }), base, "a new login gets a new box");
});

test("a stored answer is shown only for the identity it was loaded for", () => {
  const id1 = identityOf("job-1");
  const id2 = identityOf("job-2");
  const stored = labelled(id1, { accuracy: 0.913 });
  assert.deepEqual(valueFor(stored, id1), { accuracy: 0.913 });
  assert.equal(valueFor(stored, id2), null, "after switching to job-2 nothing of job-1 is shown");
  assert.equal(valueFor(null, id1), null);
});

test("Hilal's case: job-1 shown, switch to job-2 while its answer is delayed -> loading, never job-1's 91.3%", async () => {
  // The same steps JobResults takes, with a slow answer for job-2.
  let releaseJob2;
  const api = {
    getExperimentByName: async () => ({ status: 200, body: FIXTURE_EXPERIMENT }),
    searchRuns: (request) => {
      const isJob2 = request.filter.includes("'job-2'");
      const run = isJob2
        ? fixtureRun({ runId: "r2", jobId: "job-2", projectId: "project-2", metrics: [{ key: "final_accuracy", value: 0.5 }] })
        : fixtureRun({ runId: "r1", jobId: "job-1", projectId: "project-1", metrics: [{ key: "final_accuracy", value: 0.913 }] });
      const answer = { status: 200, body: { runs: [run] } };
      return isJob2 ? new Promise((resolve) => (releaseJob2 = () => resolve(answer))) : Promise.resolve(answer);
    },
  };

  let stored = null;
  const id1 = resultsIdentity({ job: job1, api });
  stored = labelled(id1, await loadJobResults({ api, job: job1 }));
  assert.equal(valueFor(stored, id1).latest.metrics.final_accuracy.value, 0.913);

  // Switch to job-2. Its answer has not arrived yet.
  const id2 = resultsIdentity({ job: job2, api });
  const pending = loadJobResults({ api, job: job2 });
  assert.equal(valueFor(stored, id2), null, "job-2 shows loading, not job-1's results");

  // A late answer for job-1 (from before the switch) must not appear under job-2 either.
  const late = labelled(id1, await loadJobResults({ api, job: job1 }));
  assert.equal(valueFor(late, id2), null);

  releaseJob2();
  stored = labelled(id2, await pending);
  const shown = valueFor(stored, id2);
  assert.equal(shown.state, RESULT_STATES.READY);
  assert.equal(shown.latest.tags.job_id, "job-2");
  assert.equal(shown.latest.metrics.final_accuracy.value, 0.5);
});
