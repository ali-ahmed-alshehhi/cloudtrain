"use client";
// Job alerts panel (owner: Adel): the portal's notification area (docs/decisions/0002).
// Shows the newest events first and marks the ones that arrived since the last poll.
//
//   const feedState = useAlertFeed({ fetchEvents, projectId });
//   <JobAlerts feedState={feedState} renderJobLink={(jobId) => <a href={`/jobs/${jobId}`}>{jobId}</a>} />
//
// `renderJobLink` is optional: Hilal's pages decide where a job link goes.

import { describeEvent, phaseMessage } from "../../lib/alerts/describe.mjs";
import { MESSAGE_STYLES, TONE_STYLES } from "./tones";

export default function JobAlerts({ feedState, max = 20, renderJobLink, title = "Job alerts" }) {
  const message = phaseMessage(feedState);
  const fresh = new Set((feedState?.newEvents ?? []).map((e) => e.event_id));
  const events = [...(feedState?.events ?? [])].reverse().slice(0, max);

  return (
    <section aria-label={title} data-testid="job-alerts" data-phase={feedState?.phase ?? "loading"}>
      <h2 style={{ fontSize: 18, margin: "0 0 8px" }}>{title}</h2>
      {message && (
        <p role={message.kind === "info" ? undefined : "alert"} style={{ margin: "4px 0", ...MESSAGE_STYLES[message.kind] }}>
          {message.text}
        </p>
      )}
      {events.length > 0 && (
        <ul aria-live="polite" style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {events.map((event) => {
            const { title: line, details, tone } = describeEvent(event);
            const style = TONE_STYLES[tone];
            const isNew = fresh.has(event.event_id);
            return (
              <li
                key={event.event_id}
                data-new={isNew ? "true" : undefined}
                style={{
                  borderLeft: `4px solid ${style.border}`,
                  background: isNew ? style.background : "transparent",
                  padding: "6px 10px",
                  margin: "4px 0",
                }}
              >
                <time dateTime={event.occurred_at} style={{ color: "#64748b", fontSize: 13, marginRight: 8 }}>
                  {formatTime(event.occurred_at)}
                </time>
                {isNew && <strong style={{ marginRight: 6 }}>New:</strong>}
                {renderJobLink ? withLink(line, event.job_id, renderJobLink) : line}
                {details.length > 0 && <span style={{ color: "#475569" }}> ({details.join(" · ")})</span>}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function withLink(line, jobId, renderJobLink) {
  if (!jobId || !line.startsWith(jobId)) return line;
  return (
    <>
      {renderJobLink(jobId)}
      {line.slice(jobId.length)}
    </>
  );
}

// Shown in UTC, the same as the contract's timestamps, so it never depends on the server's clock zone.
function formatTime(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso ?? "";
  return `${date.toISOString().slice(0, 16).replace("T", " ")} UTC`;
}
