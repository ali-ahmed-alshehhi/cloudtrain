"use client";
// GPU-hours and estimated cost of a whole project (owner: Adel). For Hilal's project page.
//
//   const jobsApi = useMemo(() => makeJobsApi({ gatewayUrl, authToken }), [gatewayUrl, authToken]);
//   <ProjectUsage projectId={projectId} api={jobsApi} renderJobLink={(id) => <a href={`/jobs/${id}`}>{id}</a>} />
//
// Loads GET /api/v1/jobs?project_id=… once, and every 30 s while a job is running. Switching project or
// login shows "Loading…" at once: the box is keyed by that identity (same rule as JobResults, #98).

import { useEffect, useState } from "react";

import { identityOf, labelled, valueFor } from "../../lib/identity.mjs";
import {
  COST_NOTE,
  STAGES,
  USAGE_STATES,
  describeJobUsage,
  describeProjectTotal,
  loadProjectUsage,
  usageMessage,
} from "../../lib/usage/cost.mjs";
import { MESSAGE_STYLES } from "../alerts/tones";

const RELOAD_WHILE_RUNNING_MS = 30000;
const cell = { padding: "4px 16px 4px 0", textAlign: "left" };
const num = { ...cell, textAlign: "right", fontVariantNumeric: "tabular-nums" };

export default function ProjectUsage(props) {
  const identity = identityOf(props.projectId, props.api);
  return <UsageBox key={identity} identity={identity} {...props} />;
}

function UsageBox({ identity, projectId, api, renderJobLink }) {
  const [stored, setStored] = useState(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!api || !projectId) return undefined;
    let cancelled = false;
    loadProjectUsage({ api, projectId }).then((loaded) => {
      if (!cancelled) setStored(labelled(identity, loaded));
    });
    return () => {
      cancelled = true;
    };
  }, [identity, tick]); // identity covers api and projectId

  const result = valueFor(stored, identity);

  useEffect(() => {
    if (!(result?.usage?.running > 0)) return undefined;
    const timer = setTimeout(() => setTick((t) => t + 1), RELOAD_WHILE_RUNNING_MS);
    return () => clearTimeout(timer);
  }, [result]);

  const message = usageMessage(result);
  const usage = result?.state === USAGE_STATES.READY ? result.usage : null;
  const total = usage ? describeProjectTotal(usage) : null;

  return (
    <section aria-label="Project usage and cost" data-testid="project-usage" data-state={result?.state ?? "loading"}>
      <h2 style={{ fontSize: 18, margin: "0 0 8px" }}>Usage and cost</h2>
      {message && (
        <p role={message.kind === "info" ? undefined : "alert"} style={{ margin: "4px 0", ...MESSAGE_STYLES[message.kind] }}>
          {message.text}
        </p>
      )}
      {usage && usage.jobs > 0 && (
        <>
          <p style={{ margin: "4px 0 8px", fontSize: 16 }}>
            <strong>{total.cost}</strong> estimated · <strong>{total.gpuHours}</strong> GPU-hours · {usage.jobs} job
            {usage.jobs === 1 ? "" : "s"}
          </p>
          <table style={{ borderCollapse: "collapse", fontSize: 14 }}>
            <thead>
              <tr style={{ borderBottom: "1px solid #e4e3df" }}>
                <th style={cell}>Job</th>
                <th style={cell}>Status</th>
                <th style={cell}>Machine</th>
                <th style={num}>GPU-hours</th>
                <th style={num}>Estimated cost</th>
              </tr>
            </thead>
            <tbody>
              {usage.rows.map((row) => {
                const words = describeJobUsage(row);
                return (
                  <tr key={row.jobId} data-stage={row.stage}>
                    <td style={cell}>{renderJobLink ? renderJobLink(row.jobId) : row.jobId}</td>
                    <td style={cell}>{row.status}</td>
                    <td style={{ ...cell, color: "#475569" }}>{row.machineType ?? "—"}</td>
                    <td style={num}>{words.gpuHours}</td>
                    <td style={{ ...num, color: row.costKnown || row.stage === STAGES.NOT_STARTED ? undefined : "#7c4a03" }}>
                      {words.cost}
                    </td>
                  </tr>
                );
              })}
            </tbody>
            <tfoot>
              <tr style={{ borderTop: "1px solid #e4e3df", fontWeight: 600 }}>
                <td style={cell} colSpan={3}>
                  Total
                </td>
                <td style={num}>{total.gpuHours}</td>
                <td style={num}>{total.cost}</td>
              </tr>
            </tfoot>
          </table>
          <p style={{ margin: "6px 0 0", fontSize: 12, color: "#64748b" }}>{COST_NOTE}</p>
        </>
      )}
    </section>
  );
}
