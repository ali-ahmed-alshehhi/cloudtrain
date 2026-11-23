import JobDetail from "../../../components/jobs/JobDetail";
import { localDevToken } from "../../lib/dev-session.mjs";
export const dynamic = "force-dynamic";
export default async function Page({ params }) {
  const { jobId } = await params;
  return <JobDetail gatewayUrl={process.env.NEXT_PUBLIC_GATEWAY_URL || "http://localhost:5810"} devToken={localDevToken(process.env)} jobId={jobId} />;
}
