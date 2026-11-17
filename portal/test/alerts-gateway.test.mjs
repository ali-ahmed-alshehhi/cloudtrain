import assert from "node:assert/strict";
import { test } from "node:test";

import { makeFetchEvents } from "../lib/alerts/gateway.mjs";
import { fixtureError } from "./fixtures/job-events.fixture.mjs";

function fakeFetch(status, body) {
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({ url, options });
    return {
      status,
      json: async () => {
        if (body === undefined) throw new SyntaxError("not JSON");
        return body;
      },
    };
  };
  return { calls, fetchImpl };
}

test("calls only the gateway's /api/v1/jobs/events with the token and the query", async () => {
  const { calls, fetchImpl } = fakeFetch(200, { items: [], last_event_id: null });
  const fetchEvents = makeFetchEvents({ gatewayUrl: "http://localhost:5810/", authToken: "t0k", fetchImpl });
  const answer = await fetchEvents({ after: "event-3", project_id: "project-01", limit: 200 });
  assert.deepEqual(answer, { status: 200, body: { items: [], last_event_id: null } });
  assert.equal(calls[0].url, "http://localhost:5810/api/v1/jobs/events?after=event-3&project_id=project-01&limit=200");
  assert.equal(calls[0].options.headers.Authorization, "Bearer t0k");
});

test("no token: no Authorization header (real login adds it later)", async () => {
  const { calls, fetchImpl } = fakeFetch(401, fixtureError("UNAUTHORIZED", "Log in first"));
  const answer = await makeFetchEvents({ gatewayUrl: "http://gw", fetchImpl })({ after: null });
  assert.equal(answer.status, 401);
  assert.equal(answer.body.error.code, "UNAUTHORIZED");
  assert.deepEqual(calls[0].options.headers, {});
});

test("a non-JSON error page still gives its status, with body null", async () => {
  const { fetchImpl } = fakeFetch(502, undefined);
  assert.deepEqual(await makeFetchEvents({ gatewayUrl: "http://gw", fetchImpl })({}), { status: 502, body: null });
});

test("network down: the promise rejects (the feed shows 'unavailable')", async () => {
  const fetchImpl = async () => {
    throw new TypeError("fetch failed");
  };
  await assert.rejects(makeFetchEvents({ gatewayUrl: "http://gw", fetchImpl })({}), TypeError);
});
