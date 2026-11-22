"use client";

import { useAlertFeed } from "../../components/alerts/useAlertFeed";
import JobAlerts from "../../components/alerts/JobAlerts";

export default function ProjectAlerts({ api, projectId }) {
  const feedState = useAlertFeed({ fetchEvents: api.fetchEvents, projectId });
  return <JobAlerts feedState={feedState} />;
}
