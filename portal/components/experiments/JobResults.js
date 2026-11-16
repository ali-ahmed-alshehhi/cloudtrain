"use client";
// Training results of one job, read from MLflow through the gateway (owner: Adel).
//
//   const experimentsApi = useMemo(() => makeExperimentsApi({ gatewayUrl, authToken }), [gatewayUrl, authToken]);
//   <JobResults job={job} api={experimentsApi} liveStatus={liveStatus} />
//
// `job` is GET /api/v1/jobs/{id}. `liveStatus` (optional) is the status from <LiveJobStatus>'s feed;
// when it changes (for example RUNNING -> SUCCEEDED) the results load again. While the newest run is
// RUNNING they also reload every 30 seconds.
//
// Results never show under the wrong job: switching job, project, experiment or API client (a new
// login) mounts a fresh box (the `key` below), and every stored answer is labelled with the identity it
// was loaded for and shown only while that identity is current (lib/identity.mjs).

import { useEffect, useState } from "react";

import { labelled, valueFor } from "../../lib/identity.mjs";
import {
  CHART_METRICS,
  KNOWN_METRICS,
  RESULT_STATES,
  describeParallelism,
  formatDuration,
  formatMetric,
  loadJobResults,
  loadMetricHistory,
  resultsIdentity,
  resultsMessage,
  summarizeMetrics,
} from "../../lib/experiments/mlflow.mjs";
import { MESSAGE_STYLES } from "../alerts/tones";
import MetricChart from "./MetricChart";

const RELOAD_WHILE_RUNNING_MS = 30000;
const RUN_STATUS_WORDS = { RUNNING: "running", SCHEDULED: "scheduled", FINISHED: "finished", FAILED: "failed", KILLED: "stopped" };

export default function JobResults(props) {
  const identity = resultsIdentity(props);
  return <ResultsBox key={identity} identity={identity} {...props} />;
}

function ResultsBox({ identity, job, api, liveStatus = null, experimentName }) {
  const [stored, setStored] = useState(null); // labelled(identity, result)
  const [chosen, setChosen] = useState(null); // labelled(identity, runId)
  const [history, setHistory] = useState(null); // labelled(identity, { runId, points })
  const [tick, setTick] = useState(0);
  const jobStatus = liveStatus ?? job?.status ?? null;

  // Load the job's runs.
  useEffect(() => {
    if (!api || !job) return undefined;
    let cancelled = false;
    loadJobResults({ api, job, experimentName }).then((loaded) => {
      if (!cancelled) setStored(labelled(identity, loaded));
    });
    return () => {
      cancelled = true;
    };
  }, [identity, jobStatus, tick]); // identity covers api, job_id, project_id and experimentName

  const result = valueFor(stored, identity);
  const chosenRunId = valueFor(chosen, identity);
  const setChosenRunId = (runId) => setChosen(labelled(identity, runId));
  const runs = result?.runs ?? [];
  const run = runs.find((r) => r.runId === chosenRunId) ?? result?.latest ?? null;

  // Reload while the newest run is still training.
  useEffect(() => {
    if (result?.latest?.status !== "RUNNING") return undefined;
    const timer = setTimeout(() => setTick((t) => t + 1), RELOAD_WHILE_RUNNING_MS);
    return () => clearTimeout(timer);
  }, [result]);

  // Load the per-epoch history of the shown run.
  useEffect(() => {
    if (!api || !run?.runId) return undefined;
    let cancelled = false;
    loadMetricHistory({ api, runId: run.runId }).then((loaded) => {
      if (!cancelled) setHistory(labelled(identity, { runId: run.runId, points: loaded }));
    });
    return () => {
      cancelled = true;
    };
  }, [identity, run?.runId, run?.metrics]);

  const message = resultsMessage(result, jobStatus);
  const rows = run ? summarizeMetrics(run) : [];
  const shownHistory = valueFor(history, identity);
  const charts = shownHistory && run && shownHistory.runId === run.runId ? shownHistory.points : null;
  const details = run
    ? [
        `MLflow run ${RUN_STATUS_WORDS[run.status] ?? run.status ?? "status unknown"}`,
        describeParallelism(run),
        formatDuration(run.durationSeconds) && `took ${formatDuration(run.durationSeconds)}`,
        run.startTime && `started ${new Date(run.startTime).toISOString().slice(0, 16).replace("T", " ")} UTC`,
      ].filter(Boolean)
    : [];

  return (
    <section aria-label="Training results" data-testid="job-results" data-state={result?.state ?? "loading"}>
      <h2 style={{ fontSize: 18, margin: "0 0 8px" }}>Training results (MLflow)</h2>
      {message && (
        <p role={message.kind === "info" ? undefined : "alert"} style={{ margin: "4px 0", ...MESSAGE_STYLES[message.kind] }}>
          {message.text}
        </p>
      )}

      {result?.state === RESULT_STATES.READY && run && (
        <>
          {runs.length > 1 && (
            <div role="group" aria-label="Attempt" style={{ display: "flex", gap: 6, margin: "4px 0 8px", flexWrap: "wrap" }}>
              {runs.map((r) => (
                <button
                  key={r.runId}
                  type="button"
                  aria-pressed={r.runId === run.runId}
                  onClick={() => setChosenRunId(r.runId)}
                  style={{
                    padding: "2px 10px",
                    borderRadius: 6,
                    border: "1px solid #cbd5e1",
                    background: r.runId === run.runId ? "#0b0b0b" : "white",
                    color: r.runId === run.runId ? "white" : "#0b0b0b",
                    cursor: "pointer",
                  }}
                >
                  Attempt {r.attempt} ({RUN_STATUS_WORDS[r.status] ?? r.status})
                </button>
              ))}
            </div>
          )}

          <p style={{ margin: "4px 0 8px", color: "#475569", fontSize: 14 }}>{details.join(" · ")}</p>

          {rows.length === 0 ? (
            <p style={{ color: "#475569" }}>This run has not logged any metrics yet.</p>
          ) : (
            <table style={{ borderCollapse: "collapse", marginBottom: 12, fontSize: 14 }}>
              <thead>
                <tr style={{ borderBottom: "1px solid #e4e3df" }}>
                  <th style={{ textAlign: "left", padding: "4px 16px 4px 0" }}>Metric</th>
                  <th style={{ textAlign: "right", padding: "4px 16px 4px 0" }}>Value</th>
                  <th style={{ textAlign: "left", padding: "4px 0" }}>From</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.key}>
                    <td style={{ padding: "4px 16px 4px 0" }}>
                      {row.label}
                      {row.better && <span style={{ color: "#64748b" }}> ({row.better} is better)</span>}
                    </td>
                    <td style={{ textAlign: "right", padding: "4px 16px 4px 0", fontVariantNumeric: "tabular-nums", fontWeight: 600 }}>
                      {formatMetric(row.value, row.kind)}
                    </td>
                    <td style={{ color: "#64748b" }}>
                      {row.final ? "final" : row.step !== null ? `latest, epoch ${row.step}` : "latest"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {charts && (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 16 }}>
              {CHART_METRICS.map((key) => {
                const known = KNOWN_METRICS.find((m) => m.key === key);
                if (charts[key] === null) {
                  return (
                    <p key={key} style={{ fontSize: 13, ...MESSAGE_STYLES.warning }}>
                      {known.label}: history unavailable right now.
                    </p>
                  );
                }
                if (charts[key].length < 2) return null; // one point is not a trend; the table shows it
                return <MetricChart key={key} title={known.label} points={charts[key]} kind={known.kind} />;
              })}
            </div>
          )}
        </>
      )}
    </section>
  );
}
