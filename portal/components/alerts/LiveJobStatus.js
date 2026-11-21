"use client";
// Live status badge for one job (owner: Adel). Hilal's job page passes the job it loaded with
// GET /api/v1/jobs/{id} and the shared alert-feed state; the badge updates when a newer event arrives.
//
//   <LiveJobStatus job={job} feedState={feedState} />

import { latestJobStatus, statusLabel, statusTone } from "../../lib/alerts/describe.mjs";
import { TONE_STYLES } from "./tones";

export default function LiveJobStatus({ job, feedState, showDetails = true }) {
  const live = latestJobStatus(job, feedState?.events ?? []);
  const tone = TONE_STYLES[statusTone(live.status)];
  const details = [];
  if (live.attempt > 1) details.push(`attempt ${live.attempt}`);
  if (live.machine_type) details.push(live.machine_type);
  if (live.reason && (live.status === "FAILED" || live.status === "CANCELLED")) details.push(live.reason);

  return (
    <span data-testid="live-job-status" data-status={live.status ?? ""}>
      <span
        role="status"
        aria-live="polite"
        style={{
          display: "inline-block",
          padding: "2px 10px",
          borderRadius: 999,
          border: `1px solid ${tone.border}`,
          background: tone.background,
          color: tone.color,
          fontWeight: 600,
          fontSize: 14,
        }}
      >
        {statusLabel(live.status)}
      </span>
      {showDetails && details.length > 0 && (
        <span style={{ marginLeft: 8, color: "#475569", fontSize: 14 }}>{details.join(" · ")}</span>
      )}
    </span>
  );
}
