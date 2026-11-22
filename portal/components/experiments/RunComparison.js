"use client";
// 1 GPU vs multi-GPU DDP comparison for one project (owner: Adel). For Hilal's comparison page.
//
//   const experimentsApi = useMemo(() => makeExperimentsApi({ gatewayUrl, authToken }), [gatewayUrl, authToken]);
//   const jobsApi = useMemo(() => makeJobsApi({ gatewayUrl, authToken }), [gatewayUrl, authToken]);
//   <RunComparison projectId={projectId} experimentsApi={experimentsApi} jobsApi={jobsApi} />
//
// Same arithmetic as docs/BENCHMARKS.md (lib/experiments/compare.mjs). Switching project or login shows
// "Loading…" at once (keyed box, lib/identity.mjs).

import { useEffect, useState } from "react";

import { identityOf, labelled, valueFor } from "../../lib/identity.mjs";
import {
  COMPARE_STATES,
  comparisonMessage,
  formatEfficiency,
  formatSeconds,
  formatSpeedup,
  formatThroughput,
  loadComparison,
} from "../../lib/experiments/compare.mjs";
import { formatMetric } from "../../lib/experiments/mlflow.mjs";
import { COST_NOTE, formatGpuHours, formatUsd } from "../../lib/usage/cost.mjs";
import { MESSAGE_STYLES } from "../alerts/tones";

const cell = { padding: "4px 14px 4px 0", textAlign: "left", whiteSpace: "nowrap" };
const num = { ...cell, textAlign: "right", fontVariantNumeric: "tabular-nums" };

export default function RunComparison(props) {
  const identity = identityOf(props.projectId, props.experimentsApi, props.jobsApi);
  return <ComparisonBox key={identity} identity={identity} {...props} />;
}

function ComparisonBox({ identity, projectId, experimentsApi, jobsApi }) {
  const [stored, setStored] = useState(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!experimentsApi || !projectId) return undefined;
    let cancelled = false;
    loadComparison({ experimentsApi, jobsApi, projectId }).then((loaded) => {
      if (!cancelled) setStored(labelled(identity, loaded));
    });
    return () => {
      cancelled = true;
    };
  }, [identity, tick]); // identity covers projectId and both API clients

  const result = valueFor(stored, identity);
  const message = comparisonMessage(result);

  return (
    <section aria-label="1 GPU vs DDP comparison" data-testid="run-comparison" data-state={result?.state ?? "loading"}>
      <h2 style={{ fontSize: 18, margin: "0 0 8px" }}>
        1 GPU vs multi-GPU (DDP){" "}
        <button type="button" onClick={() => setTick((t) => t + 1)} style={{ fontSize: 13, marginLeft: 8 }}>
          Refresh
        </button>
      </h2>
      {message && (
        <p role={message.kind === "info" ? undefined : "alert"} style={{ margin: "4px 0", ...MESSAGE_STYLES[message.kind] }}>
          {message.text}
        </p>
      )}
      {result?.state === COMPARE_STATES.READY &&
        result.groups.map((group) => (
          <div key={group.key} data-testid="comparison-group" style={{ margin: "12px 0 20px" }}>
            <h3 style={{ fontSize: 15, margin: "0 0 6px" }}>{group.label || "Unnamed workload"}</h3>
            {group.problems.map((problem) => (
              <p key={problem} style={{ margin: "2px 0", fontSize: 13, ...MESSAGE_STYLES.warning }}>
                {problem}
              </p>
            ))}
            <div style={{ overflowX: "auto" }}>
              <table style={{ borderCollapse: "collapse", fontSize: 14, marginTop: 4 }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid #e4e3df" }}>
                    <th style={cell}>GPUs</th>
                    <th style={cell}>Strategy</th>
                    <th style={num}>Runs</th>
                    <th style={num}>Time per epoch</th>
                    <th style={num}>Throughput (images/s)</th>
                    <th style={num}>Speedup</th>
                    <th style={num}>Efficiency</th>
                    <th style={num}>Total time</th>
                    <th style={num}>Final accuracy</th>
                    <th style={num}>GPU-hours</th>
                    <th style={num}>Estimated cost</th>
                  </tr>
                </thead>
                <tbody>
                  {group.rows.map((row) => (
                    <tr key={row.gpus} data-gpus={row.gpus}>
                      <td style={cell}>{row.gpus}</td>
                      <td style={cell}>{row.strategy}</td>
                      <td style={num}>{row.repeats}</td>
                      <td style={num}>{formatSeconds(row.timePerEpoch)}</td>
                      <td style={num}>{formatThroughput(row.imagesPerSecond)}</td>
                      <td style={{ ...num, fontWeight: 600 }}>{formatSpeedup(row.speedup)}</td>
                      <td style={num}>{formatEfficiency(row.efficiency)}</td>
                      <td style={num}>{row.totalSeconds === null ? "—" : formatSeconds(row.totalSeconds)}</td>
                      <td style={num}>{row.accuracy === null ? "—" : formatMetric(row.accuracy, "fraction")}</td>
                      <td style={num}>{formatGpuHours(row.gpuHours)}</td>
                      <td style={num}>{row.gpuHours === null ? "—" : formatUsd(row.cost)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      {result?.state === COMPARE_STATES.READY && (
        <p style={{ margin: "6px 0 0", fontSize: 12, color: "#64748b" }}>
          Each row is the mean of its runs. Time per epoch leaves out the first epoch (warm-up); speedup = time per
          epoch on 1 GPU ÷ on N GPUs; efficiency = speedup ÷ N, as in docs/BENCHMARKS.md. GPU-hours and cost come
          from Training Jobs (all attempts of the job). {COST_NOTE}
          {result.leftOut > 0 && ` ${result.leftOut} run(s) left out: CPU runs or runs without strategy/world_size tags.`}
        </p>
      )}
    </section>
  );
}
