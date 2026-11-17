import assert from "node:assert/strict";
import { test } from "node:test";

import {
  MAX_BACKOFF_MS,
  PAGE_LIMIT,
  PHASES,
  POLL_MS,
  createAlertFeed,
  eventsQueryString,
} from "../lib/alerts/feed.mjs";
import {
  FIXTURE_JOB_LIFE,
  FIXTURE_OTHER_PROJECT_EVENT,
  fixtureError,
  fixtureEvent,
} from "./fixtures/job-events.fixture.mjs";

// A fake gateway that answers from a list of prepared answers, and a fake clock.
function harness(answers, { projectId = "project-01" } = {}) {
  const calls = [];
  const states = [];
  const timers = [];
  const feed = createAlertFeed({
    projectId,
    fetchEvents: async (query) => {
      calls.push(query);
      const next = answers.shift();
      if (next instanceof Error) throw next;
      return next ?? { status: 200, body: { items: [], last_event_id: query.after } };
    },
    onChange: (state) => states.push(state),
    setTimer: (fn, ms) => {
      timers.push({ fn, ms });
      return timers.length;
    },
    clearTimer: () => {},
  });
  const settle = () => new Promise((resolve) => setImmediate(resolve));
  async function tick() {
    const timer = timers.shift();
    assert.ok(timer, "a next poll was planned");
    await timer.fn();
    await settle();
    return timer.ms;
  }
  return { feed, calls, states, timers, tick, settle, last: () => states.at(-1) };
}

const ok = (items, last = items.at(-1)?.event_id ?? null) => ({ status: 200, body: { items, last_event_id: last } });

test("first answer: history is loaded, not shown as new alerts; then new events become alerts", async () => {
  const h = harness([ok(FIXTURE_JOB_LIFE.slice(0, 3)), ok(FIXTURE_JOB_LIFE.slice(3))]);
  h.feed.start();
  assert.equal(h.states[0].phase, PHASES.LOADING);
  await h.settle();

  assert.equal(h.last().phase, PHASES.READY);
  assert.equal(h.last().events.length, 3);
  assert.deepEqual(h.last().newEvents, []);
  assert.deepEqual(h.calls[0], { after: null, project_id: "project-01", limit: PAGE_LIMIT });

  const waited = await h.tick();
  assert.equal(waited, POLL_MS);
  assert.equal(h.calls[1].after, "event-3", "the cursor is the last event_id seen");
  assert.deepEqual(
    h.last().newEvents.map((e) => e.event_type),
    ["job.failed", "job.retrying"],
  );
  assert.equal(h.last().lastEventId, "event-5");
});

test("empty feed: READY with no events, cursor stays null", async () => {
  const h = harness([ok([], null)]);
  h.feed.start();
  await h.settle();
  assert.equal(h.last().phase, PHASES.READY);
  assert.deepEqual(h.last().events, []);
  await h.tick();
  assert.equal(h.calls[1].after, null);
});

test("duplicate events are shown once", async () => {
  const [a, b] = FIXTURE_JOB_LIFE;
  const h = harness([ok([a, b]), ok([b, a], "event-2")]);
  h.feed.start();
  await h.settle();
  await h.tick();
  assert.equal(h.last().events.length, 2);
  assert.deepEqual(h.last().newEvents, []);
});

test("events of another project are dropped even if the server sends them", async () => {
  const h = harness([ok([FIXTURE_JOB_LIFE[0], FIXTURE_OTHER_PROJECT_EVENT])]);
  h.feed.start();
  await h.settle();
  assert.deepEqual(
    h.last().events.map((e) => e.project_id),
    ["project-01"],
  );
});

test("a full page is followed at once by the next page (catching up)", async () => {
  const fullPage = Array.from({ length: PAGE_LIMIT }, (_, i) => fixtureEvent(i + 1));
  const h = harness([ok(fullPage), ok([fixtureEvent(PAGE_LIMIT + 1)])]);
  h.feed.start();
  await h.settle();
  assert.equal(h.calls.length, 2, "two pages in one poll");
  assert.equal(h.calls[1].after, `event-${PAGE_LIMIT}`);
  assert.equal(h.last().lastEventId, `event-${PAGE_LIMIT + 1}`);
  assert.equal(h.last().events.length, 100, "only the latest KEEP_EVENTS are kept");
});

test("401 stops polling and says the user must log in", async () => {
  const h = harness([{ status: 401, body: fixtureError("UNAUTHORIZED", "Log in first") }]);
  h.feed.start();
  await h.settle();
  assert.equal(h.last().phase, PHASES.UNAUTHORIZED);
  assert.equal(h.last().error.code, "UNAUTHORIZED");
  assert.equal(h.timers.length, 0, "no further polls");
});

test("403 stops polling (not a member of the project)", async () => {
  const h = harness([{ status: 403, body: fixtureError("NOT_A_MEMBER", "Not a member of project-01") }]);
  h.feed.start();
  await h.settle();
  assert.equal(h.last().phase, PHASES.FORBIDDEN);
  assert.equal(h.timers.length, 0);
});

test("503 and network errors back off (doubling, capped), then recover to 5 s", async () => {
  const down = { status: 503, body: fixtureError("SERVICE_UNAVAILABLE", "job-service is down") };
  const h = harness([down, new TypeError("fetch failed"), down, down, down, down, ok([FIXTURE_JOB_LIFE[0]])]);
  h.feed.start();
  await h.settle();
  assert.equal(h.last().phase, PHASES.UNAVAILABLE);
  assert.equal(h.timers[0].ms, 10000);

  const waits = [];
  for (let i = 0; i < 5; i += 1) waits.push(await h.tick());
  assert.deepEqual(waits, [10000, 20000, 40000, 60000, MAX_BACKOFF_MS]);
  await h.tick();
  assert.equal(h.last().phase, PHASES.READY);
  assert.equal(h.timers[0].ms, POLL_MS, "back to the normal interval");
  assert.equal(h.last().events.length, 1);
});

test("an answer arriving after stop() is ignored (project changed)", async () => {
  let release;
  const states = [];
  const feed = createAlertFeed({
    projectId: "project-01",
    fetchEvents: () => new Promise((resolve) => (release = resolve)),
    onChange: (s) => states.push(s),
    setTimer: () => assert.fail("must not plan another poll"),
    clearTimer: () => {},
  });
  feed.start();
  feed.stop();
  release(ok(FIXTURE_JOB_LIFE));
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(states.at(-1).phase, PHASES.LOADING);
});

test("eventsQueryString builds the contract's query", () => {
  assert.equal(eventsQueryString({ after: null, project_id: null, limit: null }), "");
  assert.equal(
    eventsQueryString({ after: "event-9", project_id: "project-01", limit: 200 }),
    "?after=event-9&project_id=project-01&limit=200",
  );
});
