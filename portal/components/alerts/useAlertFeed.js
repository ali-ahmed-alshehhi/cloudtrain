"use client";
// React hook around the alert feed (owner: Adel). One feed per page: share its state between
// <JobAlerts> and every <LiveJobStatus> on the page instead of starting a second poller.
//
// `fetchEvents` must keep the same identity between renders (create it with useMemo), otherwise the
// feed restarts on every render. A new `projectId` stops the old feed and starts a fresh one.

import { useEffect, useState } from "react";

import { createAlertFeed } from "../../lib/alerts/feed.mjs";

export function useAlertFeed({ fetchEvents, projectId = null }) {
  const [state, setState] = useState(null);

  useEffect(() => {
    if (!fetchEvents) return undefined;
    const feed = createAlertFeed({ fetchEvents, projectId, onChange: setState });
    feed.start();
    return () => feed.stop();
  }, [fetchEvents, projectId]);

  return state;
}
