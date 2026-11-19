"use client";
// A small one-series line chart of a metric per epoch (owner: Adel).
// One series, so no legend: the title names it. 2px line, a dot per epoch, the last value labelled,
// a tooltip on hover/focus, and a table of the same numbers for screen readers and exact values.

import { useState } from "react";

import { formatMetric } from "../../lib/experiments/mlflow.mjs";

const W = 300;
const H = 140;
const PAD = { top: 16, right: 52, bottom: 28, left: 44 };
const COLORS = { line: "#2a78d6", text: "#0b0b0b", muted: "#52514e", grid: "#e4e3df", surface: "#fcfcfb" };

export default function MetricChart({ title, points, kind }) {
  const [hover, setHover] = useState(null);
  if (!points || points.length === 0) return null;

  const values = points.map((p) => p.value).filter(Number.isFinite);
  if (values.length === 0) return null;
  let low = Math.min(...values);
  let high = Math.max(...values);
  if (kind === "fraction") {
    low = Math.max(0, Math.floor(low * 10) / 10);
    high = Math.min(1, Math.ceil(high * 10) / 10);
  } else if (low > 0) {
    low = 0; // losses and counts start at 0, so the slope is not exaggerated
  }
  if (low === high) {
    low -= Math.abs(low) * 0.1 || 0.1;
    high += Math.abs(high) * 0.1 || 0.1;
  }
  const steps = points.map((p) => p.step);
  const first = Math.min(...steps);
  const last = Math.max(...steps);
  const x = (step) => PAD.left + (last === first ? 0.5 : (step - first) / (last - first)) * (W - PAD.left - PAD.right);
  const y = (value) => PAD.top + (1 - (value - low) / (high - low)) * (H - PAD.top - PAD.bottom);
  const drawn = points.filter((p) => Number.isFinite(p.value));
  const path = drawn.map((p, i) => `${i ? "L" : "M"}${x(p.step).toFixed(1)},${y(p.value).toFixed(1)}`).join(" ");
  const end = drawn.at(-1);
  const shown = hover ?? null;

  return (
    <figure style={{ margin: 0, minWidth: 0 }}>
      <figcaption style={{ fontSize: 14, fontWeight: 600, color: COLORS.text, marginBottom: 4 }}>{title}</figcaption>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        role="img"
        aria-label={`${title} by epoch, from ${formatMetric(drawn[0].value, kind)} at epoch ${drawn[0].step} to ${formatMetric(end.value, kind)} at epoch ${end.step}`}
        style={{ background: COLORS.surface, maxWidth: W, display: "block" }}
        onMouseLeave={() => setHover(null)}
      >
        {[low, high].map((v) => (
          <g key={v}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(v)} y2={y(v)} stroke={COLORS.grid} strokeWidth="1" />
            <text x={PAD.left - 6} y={y(v) + 4} textAnchor="end" fontSize="11" fill={COLORS.muted}>
              {formatMetric(v, kind)}
            </text>
          </g>
        ))}
        <text x={x(first)} y={H - 8} textAnchor="middle" fontSize="11" fill={COLORS.muted}>
          epoch {first}
        </text>
        {last !== first && (
          <text x={x(last)} y={H - 8} textAnchor="middle" fontSize="11" fill={COLORS.muted}>
            epoch {last}
          </text>
        )}
        <path d={path} fill="none" stroke={COLORS.line} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        {drawn.map((p) => (
          <g key={p.step}>
            <circle cx={x(p.step)} cy={y(p.value)} r="4" fill={COLORS.line} stroke={COLORS.surface} strokeWidth="2" />
            {/* bigger invisible hit target for hover and keyboard focus */}
            <circle
              cx={x(p.step)}
              cy={y(p.value)}
              r="12"
              fill="transparent"
              tabIndex={0}
              aria-label={`epoch ${p.step}: ${formatMetric(p.value, kind)}`}
              onMouseEnter={() => setHover(p)}
              onFocus={() => setHover(p)}
              onBlur={() => setHover(null)}
            />
          </g>
        ))}
        <text x={x(end.step) + 8} y={y(end.value) + 4} fontSize="12" fontWeight="600" fill={COLORS.text}>
          {formatMetric(end.value, kind)}
        </text>
        {shown && (
          <g pointerEvents="none">
            <line x1={x(shown.step)} x2={x(shown.step)} y1={PAD.top} y2={H - PAD.bottom} stroke={COLORS.muted} strokeDasharray="2 3" />
            <rect x={Math.min(x(shown.step) + 6, W - 110)} y={2} width="104" height="20" rx="4" fill={COLORS.text} />
            <text x={Math.min(x(shown.step) + 12, W - 104)} y={16} fontSize="11" fill={COLORS.surface}>
              epoch {shown.step}: {formatMetric(shown.value, kind)}
            </text>
          </g>
        )}
      </svg>
      <details style={{ fontSize: 13, color: COLORS.muted }}>
        <summary>Show as table</summary>
        <table style={{ borderCollapse: "collapse", marginTop: 4 }}>
          <thead>
            <tr>
              <th style={{ textAlign: "left", paddingRight: 12 }}>Epoch</th>
              <th style={{ textAlign: "right" }}>{title}</th>
            </tr>
          </thead>
          <tbody>
            {points.map((p) => (
              <tr key={p.step}>
                <td style={{ paddingRight: 12 }}>{p.step}</td>
                <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{formatMetric(p.value, kind)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
