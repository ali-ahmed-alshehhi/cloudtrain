// STAND-IN for the CloudTrain portal (owners: Hilal + Adel). Replace it; keep calling ONLY the gateway.
//
// This page is built on the server at each visit, so it can read the settings from environment
// variables at run time (one Docker image works everywhere). The browser then calls the gateway.
import Dashboard from "./dashboard";

export const dynamic = "force-dynamic";

export default function Home() {
  const gatewayUrl = process.env.NEXT_PUBLIC_GATEWAY_URL || "http://localhost:5810";
  // Local development only: the fixed test token. With real login (Salem) the user signs in instead.
  const devToken = process.env.AUTH_MODE === "dev" ? process.env.DEV_AUTH_TOKEN || "" : "";
  return <Dashboard gatewayUrl={gatewayUrl} devToken={devToken} />;
}
