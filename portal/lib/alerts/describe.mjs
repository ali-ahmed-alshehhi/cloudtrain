// Words and colours for job statuses and alerts (owner: Adel, Student 10 split 2).
// Plain JavaScript with no React, so it is tested with `node --test`.

import { PHASES } from "./feed.mjs";

// contracts/job-states.md
export const STATUS_LABELS = Object.freeze({
  QUEUED: "Queued",
  SCHEDULED: "Scheduled",
  RUNNING: "Running",
  SUCCEEDED: "Succeeded",
  FAILED: "Failed",
  CANCELLED: "Cancelled",
});

const STATUS_TONES = {
  QUEUED: "waiting",
  SCHEDULED: "waiting",
  RUNNING: "active",
  SUCCEEDED: "good",
  FAILED: "bad",
  CANCELLED: "muted",
};

const EVENT_WORDS = {
  "job.queued": "is queued",
  "job.scheduled": "was placed on a machine",
  "job.running": "started training",
  "job.succeeded": "succeeded",
  "job.failed": "failed",
  "job.cancelled": "was cancelled",
  "job.retrying": "is being retried",
};

/** "Running", or the raw value for a status this portal does not know yet. */
export function statusLabel(status) {
  return STATUS_LABELS[status] ?? String(status ?? "Unknown");
}

/** waiting | active | good | bad | muted | unknown */
export function statusTone(status) {
  return STATUS_TONES[status] ?? "unknown";
}

/** One alert line: { title, details: [..], tone }. Only shows fields the event really has. */
export function describeEvent(event) {
  const data = event?.data ?? {};
  const tone = event?.event_type === "job.retrying" ? "waiting" : statusTone(data.status);
  const details = [];
  if (data.reason) details.push(data.reason);
  if (Number.isInteger(data.attempt) && data.attempt > 1) details.push(`attempt ${data.attempt}`);
  if (data.machine_type) details.push(data.machine_type);
  const words = EVENT_WORDS[event?.event_type] ?? event?.event_type ?? "changed";
  return { title: `${event?.job_id ?? "A job"} ${words}`, details, tone };
}

/**
 * The message to show instead of (or above) the alert list, or null when there is nothing to say.
 * kind: info | warning | error
 */
export function phaseMessage(state) {
  if (!state || state.phase === PHASES.LOADING) return { kind: "info", text: "Loading job alerts…" };
  switch (state.phase) {
    case PHASES.UNAUTHORIZED:
      return { kind: "error", text: "Please log in again to see job alerts." };
    case PHASES.FORBIDDEN:
      return { kind: "error", text: "You are not a member of this project, so its job alerts are hidden." };
    case PHASES.UNAVAILABLE:
      return {
        kind: "warning",
        text: `Job alerts are unavailable right now. Trying again in ${seconds(state.nextPollMs)}.`,
      };
    case PHASES.ERROR:
      return {
        kind: "warning",
        text: `Could not load job alerts${state.error?.message ? `: ${state.error.message}` : ""}. Trying again in ${seconds(state.nextPollMs)}.`,
      };
    default:
      return state.events.length === 0 ? { kind: "info", text: "No job events yet." } : null;
  }
}

function seconds(ms) {
  return ms ? `${Math.round(ms / 1000)} s` : "a moment";
}

function eventNumber(event) {
  return Number(String(event?.event_id ?? "").replace("event-", "")) || 0;
}

/**
 * The freshest known status of one job.
 * `job` is the answer of GET /api/v1/jobs/{id} (Hilal's job page loads it); `events` comes from the
 * alert feed. The newest event of this job wins when it happened after the job was loaded.
 * Returns { status, attempt, machine_type, reason, source: "job" | "event" }.
 */
export function latestJobStatus(job, events = []) {
  const fromJob = {
    status: job?.status ?? null,
    attempt: job?.attempt ?? null,
    machine_type: job?.machine_type ?? null,
    reason: job?.history?.at(-1)?.reason ?? null,
    source: "job",
  };
  const mine = events.filter((e) => e?.job_id === job?.job_id && e?.data?.status);
  if (mine.length === 0) return fromJob;
  const newest = mine.reduce((a, b) => (eventNumber(b) > eventNumber(a) ? b : a));
  const loadedAt = Date.parse(job?.updated_at ?? "");
  const happenedAt = Date.parse(newest.occurred_at);
  if (!Number.isNaN(loadedAt) && !Number.isNaN(happenedAt) && happenedAt < loadedAt) return fromJob;
  return {
    status: newest.data.status,
    attempt: newest.data.attempt ?? fromJob.attempt,
    machine_type: newest.data.machine_type ?? fromJob.machine_type,
    reason: newest.data.reason ?? null,
    source: "event",
  };
}
