// Regression: after switching project (or connection), the previous project's alerts are never shown.
import assert from "node:assert/strict";
import { test } from "node:test";

import { PHASES, createAlertFeed, stateForFeed } from "../lib/alerts/feed.mjs";
import { fixtureEvent } from "./fixtures/job-events.fixture.mjs";

const fetchA = async () => ({ status: 200, body: { items: [], last_event_id: null } });
const fetchB = async () => ({ status: 200, body: { items: [], last_event_id: null } });

test("stateForFeed shows a state only for the project and fetchEvents it came from", () => {
  const state = { phase: PHASES.READY, events: [] };
  const stored = { projectId: "project-01", fetchEvents: fetchA, state };
  assert.equal(stateForFeed(stored, "project-01", fetchA), state);
  assert.equal(stateForFeed(stored, "project-02", fetchA), null, "another project: loading");
  assert.equal(stateForFeed(stored, "project-01", fetchB), null, "new connection/login: loading");
  assert.equal(stateForFeed(stored, null, fetchA), null, "all projects is a different view");
  assert.equal(stateForFeed(null, "project-01", fetchA), null);
  assert.equal(stateForFeed({ projectId: null, fetchEvents: fetchA, state }, undefined, fetchA), state);
});

test("switching project: project-01's events never show while project-02's first answer is delayed", async () => {
  let release;
  const fetchEvents = ({ project_id }) =>
    project_id === "project-02"
      ? new Promise((resolve) => (release = resolve))
      : Promise.resolve({ status: 200, body: { items: [fixtureEvent(10, { job_id: "job-111" })], last_event_id: "event-10" } });

  // What useAlertFeed does: keep { projectId, fetchEvents, state } from the latest feed callback.
  let stored = null;
  const start = (projectId) => {
    const feed = createAlertFeed({
      fetchEvents,
      projectId,
      onChange: (state) => (stored = { projectId, fetchEvents, state }),
      setTimer: () => 0,
      clearTimer: () => {},
    });
    feed.start();
    return feed;
  };

  const first = start("project-01");
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(stateForFeed(stored, "project-01", fetchEvents).events[0].job_id, "job-111");

  // The page re-renders with project-02 before the new feed has even started: nothing of project-01.
  assert.equal(stateForFeed(stored, "project-02", fetchEvents), null);

  first.stop();
  start("project-02");
  assert.equal(stateForFeed(stored, "project-02", fetchEvents).phase, PHASES.LOADING);
  release({ status: 200, body: { items: [fixtureEvent(20, { project_id: "project-02", job_id: "job-222" })], last_event_id: "event-20" } });
  await new Promise((resolve) => setImmediate(resolve));
  const shown = stateForFeed(stored, "project-02", fetchEvents);
  assert.deepEqual(shown.events.map((e) => e.job_id), ["job-222"]);
});
