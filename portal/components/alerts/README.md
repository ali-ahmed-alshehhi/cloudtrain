# Job alerts and live status (owner: Adel, Student 10 split 2)

Pieces for Hilal's pages. They call only the gateway: `GET /api/v1/jobs/events`
(`contracts/openapi/job-service.yaml`, `listRecentEvents`).

| File | What it is |
|---|---|
| `../../lib/alerts/feed.mjs` | The poller: cursor, catch-up paging, dedupe, project filter, 401/403/503, back-off 5 s → 60 s |
| `../../lib/alerts/describe.mjs` | Words and tones for statuses and events; `latestJobStatus(job, events)` |
| `../../lib/alerts/gateway.mjs` | `makeFetchEvents(...)`: the one call the feed needs (swap for Hilal's shared client later) |
| `useAlertFeed.js` | React hook: one feed per page; restarts when the project changes |
| `JobAlerts.js` | The alerts panel |
| `LiveJobStatus.js` | The status badge for one job |

## How to use them on a page (for Hilal)

```jsx
"use client";
import { useMemo } from "react";
import { makeFetchEvents } from "../lib/alerts/gateway.mjs";
import { useAlertFeed } from "../components/alerts/useAlertFeed";
import JobAlerts from "../components/alerts/JobAlerts";
import LiveJobStatus from "../components/alerts/LiveJobStatus";

export default function JobDetail({ gatewayUrl, authToken, job }) {
  // useMemo: the same function every render, so the feed does not restart.
  const fetchEvents = useMemo(() => makeFetchEvents({ gatewayUrl, authToken }), [gatewayUrl, authToken]);
  const feedState = useAlertFeed({ fetchEvents, projectId: job.project_id });
  return (
    <>
      <h1>{job.job_id} <LiveJobStatus job={job} feedState={feedState} /></h1>
      <JobAlerts feedState={feedState} />
    </>
  );
}
```

Use **one** `useAlertFeed` per page and pass its state to every panel and badge on that page.
When the shared gateway client exists, give `useAlertFeed` a `fetchEvents` built on it with the same
shape: `({ after, project_id, limit }) => Promise<{ status, body }>`, rejecting only on network errors.

## States the panel shows
Loading · no events yet · list (newest first, new ones marked "New:") · "please log in again" (401,
polling stops) · "not a member" (403, polling stops) · "unavailable, trying again in N s" (503 or no network).

## Test
`cd portal && npm test`. Test data in `test/fixtures/` is marked **FIXTURE** and checked against
`contracts/events/job-event.schema.json`.
