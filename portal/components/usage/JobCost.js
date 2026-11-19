"use client";
// GPU-hours and estimated cost of one job (owner: Adel). For Hilal's job page.
//
//   <JobCost job={job} />
//
// `job` is the answer of GET /api/v1/jobs/{id}. The box only words the backend's numbers; it never
// prices anything. While the job runs the numbers grow: reload `job` when its live status changes
// (LiveJobStatus) and the box follows.

import { COST_NOTE, describeJobUsage, jobUsage } from "../../lib/usage/cost.mjs";

export default function JobCost({ job }) {
  if (!job) return null;
  const usage = jobUsage(job);
  const words = describeJobUsage(usage);
  const gpus = usage.gpus === null ? null : usage.gpus === 0 ? "CPU only" : `${usage.gpus} GPU${usage.gpus === 1 ? "" : "s"}`;
  const machine = [usage.machineType, gpus].filter(Boolean).join(" · ");

  return (
    <section aria-label="Usage and cost" data-testid="job-cost" data-stage={usage.stage}>
      <h2 style={{ fontSize: 18, margin: "0 0 8px" }}>Usage and cost</h2>
      <dl style={{ display: "grid", gridTemplateColumns: "max-content 1fr", gap: "4px 16px", margin: 0, fontSize: 14 }}>
        <dt style={{ color: "#475569" }}>GPU-hours</dt>
        <dd style={{ margin: 0, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{words.gpuHours}</dd>
        <dt style={{ color: "#475569" }}>Estimated cost</dt>
        <dd style={{ margin: 0, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{words.cost}</dd>
        {machine && (
          <>
            <dt style={{ color: "#475569" }}>Machine</dt>
            <dd style={{ margin: 0 }}>{machine}</dd>
          </>
        )}
      </dl>
      {words.note && <p style={{ margin: "8px 0 0", fontSize: 14, color: "#475569" }}>{words.note}</p>}
      <p style={{ margin: "6px 0 0", fontSize: 12, color: "#64748b" }}>{COST_NOTE}</p>
    </section>
  );
}
