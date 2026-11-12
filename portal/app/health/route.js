// GET /health — 200 when the portal is up (shared rule for every service).
export function GET() {
  return Response.json({ status: "ok", service: "portal" });
}
