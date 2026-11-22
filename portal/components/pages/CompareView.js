"use client";
// Walk-through step 8 (owner: Adel): 1 GPU vs multi-GPU DDP runs of one project, from MLflow through the gateway.

import { useMemo } from "react";

import RunComparison from "../experiments/RunComparison";
import { makeExperimentsApi } from "../../lib/experiments/mlflow.mjs";
import { makeJobsApi } from "../../lib/usage/cost.mjs";
import WorkspacePage from "./WorkspacePage";

export default function CompareView({ gatewayUrl, devToken, requestedProject }) {
  const experimentsApi = useMemo(() => makeExperimentsApi({ gatewayUrl, authToken: devToken }), [gatewayUrl, devToken]);
  const jobsApi = useMemo(() => makeJobsApi({ gatewayUrl, authToken: devToken }), [gatewayUrl, devToken]);
  return <WorkspacePage gatewayUrl={gatewayUrl} devToken={devToken} active="compare" requestedProject={requestedProject}
    eyebrow="EXPERIMENTS" title="Compare runs"
    intro="Single-GPU and distributed (DDP) runs of the same workload, side by side: time per epoch, throughput, speedup, efficiency and cost.">
    {(projectId) => <RunComparison projectId={projectId} experimentsApi={experimentsApi} jobsApi={jobsApi} />}
  </WorkspacePage>;
}
