// The one call the alert feed needs: GET /api/v1/jobs/events through the gateway (owner: Adel).
//
// This is the interface the feed expects. When Hilal's shared gateway client exists, replace this
// function with one built on it; the feed does not change.
//   fetchEvents({ after, project_id, limit }) -> Promise<{ status, body }>
//   - resolves for every HTTP answer (body = parsed JSON, or null)
//   - rejects only when there is no answer at all (network down)

import { eventsQueryString } from "./feed.mjs";

export function makeFetchEvents({ gatewayUrl, authToken = "", fetchImpl = globalThis.fetch }) {
  const base = String(gatewayUrl).replace(/\/+$/, "");
  return async function fetchEvents(query) {
    const answer = await fetchImpl(`${base}/api/v1/jobs/events${eventsQueryString(query)}`, {
      headers: authToken ? { Authorization: `Bearer ${authToken}` } : {},
      cache: "no-store",
    });
    let body = null;
    try {
      body = await answer.json();
    } catch {
      body = null; // not JSON (for example an HTML error page from a load balancer)
    }
    return { status: answer.status, body };
  };
}
