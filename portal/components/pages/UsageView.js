"use client";
// Walk-through step 12 (owner: Adel): compute usage, GPU-hours and estimated cost of one project's jobs.

import { useMemo } from "react";

import ProjectUsage from "../usage/ProjectUsage";
import { makeJobsApi } from "../../lib/usage/cost.mjs";
import WorkspacePage from "./WorkspacePage";

export default function UsageView({ gatewayUrl, devToken, requestedProject }) {
  const jobsApi = useMemo(() => makeJobsApi({ gatewayUrl, authToken: devToken }), [gatewayUrl, devToken]);
  return <WorkspacePage gatewayUrl={gatewayUrl} devToken={devToken} active="usage" requestedProject={requestedProject}
    eyebrow="COMPUTE" title="Usage & cost"
    intro="Machine time, GPU-hours and the estimated cost of every job in a project, from Training Jobs.">
    {(projectId) => <ProjectUsage projectId={projectId} api={jobsApi} renderJobLink={(id) => <code style={{ whiteSpace: "nowrap" }}>{id}</code>} />}
  </WorkspacePage>;
}
