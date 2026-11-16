// FIXTURE — made-up test data, NOT real cloud or GPU results. Never show it in the portal as real.
//
// Job events shaped exactly like contracts/events/job-event.schema.json (checked by
// test/alerts-fixtures.test.mjs), for testing the alert feed before Mariam's real feed (due Fri 20 Nov).

export function fixtureEvent(n, overrides = {}) {
  return {
    event_id: `event-${n}`,
    event_type: "job.queued",
    job_id: "job-104",
    project_id: "project-01",
    occurred_at: `2026-11-20T09:${String(n % 60).padStart(2, "0")}:00Z`,
    data: { status: "QUEUED", previous_status: null, reason: null, machine_type: null, attempt: 1 },
    ...overrides,
  };
}

// One job's life, as Training Jobs would publish it.
export const FIXTURE_JOB_LIFE = [
  fixtureEvent(1),
  fixtureEvent(2, {
    event_type: "job.scheduled",
    data: { status: "SCHEDULED", previous_status: "QUEUED", reason: null, machine_type: "g4dn.xlarge", attempt: 1 },
  }),
  fixtureEvent(3, {
    event_type: "job.running",
    data: { status: "RUNNING", previous_status: "SCHEDULED", reason: null, machine_type: "g4dn.xlarge", attempt: 1 },
  }),
  fixtureEvent(4, {
    event_type: "job.failed",
    data: {
      status: "FAILED",
      previous_status: "RUNNING",
      reason: "no heartbeat for 120 seconds",
      machine_type: "g4dn.xlarge",
      attempt: 1,
    },
  }),
  fixtureEvent(5, {
    event_type: "job.retrying",
    data: { status: "QUEUED", previous_status: "FAILED", reason: "retry 1 of 2", machine_type: null, attempt: 2 },
  }),
];

// An event of another project (the feed filtered to project-01 must not show it).
export const FIXTURE_OTHER_PROJECT_EVENT = fixtureEvent(6, { project_id: "project-02", job_id: "job-200" });

// Shared error format (contracts/error-format.json).
export function fixtureError(code, message) {
  return { error: { code, message, request_id: "req-fixture" } };
}
