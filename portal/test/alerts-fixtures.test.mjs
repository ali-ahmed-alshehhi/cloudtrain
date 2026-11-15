// Checks that the test fixtures really match the shared contract, so tests built on them stay honest.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { FIXTURE_JOB_LIFE, FIXTURE_OTHER_PROJECT_EVENT } from "./fixtures/job-events.fixture.mjs";

const schema = JSON.parse(
  readFileSync(new URL("../../contracts/events/job-event.schema.json", import.meta.url), "utf8"),
);

function checkAgainstSchema(event) {
  const props = schema.properties;
  assert.deepEqual(Object.keys(event).sort(), [...schema.required].sort(), "exactly the contract's fields");
  assert.match(event.event_id, new RegExp(props.event_id.pattern));
  assert.match(event.job_id, new RegExp(props.job_id.pattern));
  assert.match(event.project_id, new RegExp(props.project_id.pattern));
  assert.ok(props.event_type.enum.includes(event.event_type), `${event.event_type} is a contract event type`);
  assert.ok(!Number.isNaN(Date.parse(event.occurred_at)) && event.occurred_at.endsWith("Z"), "ISO 8601 UTC");
  const data = props.data.properties;
  assert.ok(data.status.enum.includes(event.data.status));
  assert.ok(data.previous_status.enum.includes(event.data.previous_status));
  assert.ok(Number.isInteger(event.data.attempt) && event.data.attempt >= 1);
}

test("every fixture event matches contracts/events/job-event.schema.json", () => {
  for (const event of [...FIXTURE_JOB_LIFE, FIXTURE_OTHER_PROJECT_EVENT]) checkAgainstSchema(event);
});

test("the contract's own example passes the same check (the check itself is right)", () => {
  for (const example of schema.examples) checkAgainstSchema(example);
});
