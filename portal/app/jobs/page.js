import JobsView from "../../components/jobs/JobsView";
import { localDevToken } from "../lib/dev-session.mjs";
export const dynamic = "force-dynamic";
export default async function Page({ searchParams }) {
  const params = await searchParams;
  return <JobsView gatewayUrl={process.env.NEXT_PUBLIC_GATEWAY_URL || "http://localhost:5810"} devToken={localDevToken(process.env)} requestedProject={typeof params?.project === "string" ? params.project : ""} />;
}
