"use client";
// React hook around the alert feed (owner: Adel). One feed per page: share its state between
// <JobAlerts> and every <LiveJobStatus> on the page instead of starting a second poller.
//
// `fetchEvents` must keep the same identity between renders (create it with useMemo), otherwise the
// feed restarts on every render. A new `projectId` stops the old feed and starts a fresh one.
//
// The stored state remembers which project and fetchEvents it came from, so right after a switch the
// hook returns null ("loading") instead of the previous project's alerts, even for one frame.

import { useEffect, useState } from "react";

import { createAlertFeed, stateForFeed } from "../../lib/alerts/feed.mjs";

export function useAlertFeed({ fetchEvents, projectId = null }) {
  const [stored, setStored] = useState(null); // { projectId, fetchEvents, state }

  useEffect(() => {
    if (!fetchEvents) return undefined;
    const feed = createAlertFeed({
      fetchEvents,
      projectId,
      onChange: (state) => setStored({ projectId: projectId ?? null, fetchEvents, state }),
    });
    feed.start();
    return () => feed.stop();
  }, [fetchEvents, projectId]);

  return stateForFeed(stored, projectId, fetchEvents);
}
