// /compare (owner: Adel). Built on the server at each visit, like the projects page (app/page.js), so the
// settings come from environment variables at run time; the browser then calls the gateway only.
import CompareView from "../../components/pages/CompareView";
import { localDevToken } from "../lib/dev-session.mjs";
import { PROJECT_PARAM } from "../../lib/pages/project-choice.mjs";

export const dynamic = "force-dynamic";

export default async function Page({ searchParams }) {
  const params = await searchParams;
  const requested = typeof params?.[PROJECT_PARAM] === "string" ? params[PROJECT_PARAM] : "";
  const gatewayUrl = process.env.NEXT_PUBLIC_GATEWAY_URL || "http://localhost:5810";
  return <CompareView gatewayUrl={gatewayUrl} devToken={localDevToken(process.env)} requestedProject={requested} />;
}
