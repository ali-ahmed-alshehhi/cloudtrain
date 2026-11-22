// CloudTrain portal. All platform requests go through the gateway.
//
// This page is built on the server at each visit, so it can read the settings from environment
// variables at run time (one Docker image works everywhere). The browser then calls the gateway.
import Dashboard from "./dashboard";
import { localDevToken } from "./lib/dev-session.mjs";

export const dynamic = "force-dynamic";

export default function Home() {
  const gatewayUrl = process.env.NEXT_PUBLIC_GATEWAY_URL || "http://localhost:5810";
  // Local development only: the fixed test token. With real login (Salem) the user signs in instead.
  const devToken = localDevToken(process.env);
  return <Dashboard gatewayUrl={gatewayUrl} devToken={devToken} />;
}
