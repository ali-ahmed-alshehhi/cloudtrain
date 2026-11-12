// GET /metrics — Prometheus format (shared rule for every service). Hilal + Adel may add real metrics.
const startedAt = Date.now() / 1000;

export function GET() {
  const text = [
    "# HELP portal_up 1 when the portal is running",
    "# TYPE portal_up gauge",
    "portal_up 1",
    "# HELP portal_start_time_seconds When the portal started (Unix time)",
    "# TYPE portal_start_time_seconds gauge",
    `portal_start_time_seconds ${startedAt}`,
    "",
  ].join("\n");
  return new Response(text, { headers: { "Content-Type": "text/plain; version=0.0.4; charset=utf-8" } });
}
