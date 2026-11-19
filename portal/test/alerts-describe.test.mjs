import assert from "node:assert/strict";
import { test } from "node:test";

import {
  STATUS_LABELS,
  describeEvent,
  latestJobStatus,
  phaseMessage,
  statusLabel,
  statusTone,
} from "../lib/alerts/describe.mjs";
import { PHASES } from "../lib/alerts/feed.mjs";
import { FIXTURE_JOB_LIFE, fixtureEvent } from "./fixtures/job-events.fixture.mjs";
import { readFileSync } from "node:fs";

const schema = JSON.parse(
  readFileSync(new URL("../../contracts/events/job-event.schema.json", import.meta.url), "utf8"),
);

test("every contract status has a label and a known tone", () => {
  for (const status of schema.properties.data.properties.status.enum) {
    assert.equal(statusLabel(status), STATUS_LABELS[status]);
    assert.notEqual(statusTone(status), "unknown", status);
  }
});

test("an unknown status is shown as it is, never hidden", () => {
  assert.equal(statusLabel("PAUSED"), "PAUSED");
  assert.equal(statusTone("PAUSED"), "unknown");
  assert.equal(statusLabel(null), "Unknown");
});

test("describeEvent: failed job shows the reason and machine, in words", () => {
  const failed = FIXTURE_JOB_LIFE[3];
  assert.deepEqual(describeEvent(failed), {
    title: "job-104 failed",
    details: ["no heartbeat for 120 seconds", "g4dn.xlarge"],
    tone: "bad",
  });
});

test("describeEvent: a retry mentions the attempt; every contract event type has words", () => {
  assert.deepEqual(describeEvent(FIXTURE_JOB_LIFE[4]).details, ["retry 1 of 2", "attempt 2"]);
  for (const type of schema.properties.event_type.enum) {
    assert.doesNotMatch(describeEvent(fixtureEvent(1, { event_type: type })).title, /job\./, type);
  }
});

test("phaseMessage covers loading, empty, 401, 403, unavailable and error", () => {
  assert.match(phaseMessage(null).text, /Loading/);
  assert.match(phaseMessage({ phase: PHASES.READY, events: [] }).text, /No job events yet/);
  assert.equal(phaseMessage({ phase: PHASES.READY, events: [FIXTURE_JOB_LIFE[0]] }), null);
  assert.match(phaseMessage({ phase: PHASES.UNAUTHORIZED }).text, /log in/);
  assert.match(phaseMessage({ phase: PHASES.FORBIDDEN }).text, /not a member/);
  assert.match(phaseMessage({ phase: PHASES.UNAVAILABLE, nextPollMs: 20000 }).text, /20 s/);
  const error = phaseMessage({ phase: PHASES.ERROR, nextPollMs: 10000, error: { message: "Bad cursor" } });
  assert.equal(error.kind, "warning");
  assert.match(error.text, /Bad cursor/);
});

const job = {
  job_id: "job-104",
  status: "QUEUED",
  attempt: 1,
  machine_type: null,
  updated_at: "2026-11-20T09:01:30Z",
  history: [{ status: "QUEUED", at: "2026-11-20T09:01:00Z", reason: null }],
};

test("latestJobStatus: a newer event of this job wins over the loaded job", () => {
  const live = latestJobStatus(job, FIXTURE_JOB_LIFE.slice(0, 3));
  assert.equal(live.status, "RUNNING");
  assert.equal(live.machine_type, "g4dn.xlarge");
  assert.equal(live.source, "event");
});

test("latestJobStatus: older events and other jobs' events do not change the badge", () => {
  const older = fixtureEvent(0, { occurred_at: "2026-11-20T09:00:00Z" });
  const otherJob = fixtureEvent(9, { job_id: "job-999", data: { status: "FAILED" } });
  assert.equal(latestJobStatus(job, [older, otherJob]).source, "job");
  assert.equal(latestJobStatus(job, []).status, "QUEUED");
  assert.equal(latestJobStatus(null, []).status, null);
});

test("latestJobStatus: picks the highest event number even if events arrive out of order", () => {
  const live = latestJobStatus(job, [FIXTURE_JOB_LIFE[3], FIXTURE_JOB_LIFE[1]]);
  assert.equal(live.status, "FAILED");
  assert.equal(live.reason, "no heartbeat for 120 seconds");
});
