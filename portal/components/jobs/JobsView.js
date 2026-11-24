"use client";
import { useEffect, useMemo, useState } from "react";
import WorkspacePage from "../pages/WorkspacePage";
import { createGatewayClient } from "../../app/lib/gateway.mjs";
import Problem from "../../app/components/problem";
import { useAlertFeed } from "../alerts/useAlertFeed";
import LiveJobStatus from "../alerts/LiveJobStatus";
import JobAlerts from "../alerts/JobAlerts";
import { jobHref } from "../../lib/jobs/form.mjs";

export default function JobsView({ gatewayUrl, devToken, requestedProject }) {
  const api = useMemo(() => createGatewayClient({ gatewayUrl, getToken: () => devToken }), [gatewayUrl, devToken]);
  return <WorkspacePage gatewayUrl={gatewayUrl} devToken={devToken} requestedProject={requestedProject} active="jobs" eyebrow="TRAINING" title="Training jobs" intro="Submit a job on a fixed dataset version and follow its progress.">
    {(id) => <ProjectJobs key={`${id}:${devToken}`} api={api} projectId={id} />}
  </WorkspacePage>;
}
function ProjectJobs({ api, projectId }) {
  const feed = useAlertFeed({ fetchEvents: api.fetchEvents, projectId });
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);
  const [tick, setTick] = useState(0);
  // The one existing event feed triggers a list refresh when the job set/status changes.
  const eventId = feed?.events?.at(-1)?.event_id;
  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    api.listJobs(projectId, controller.signal).then((body) => {
      if (!Array.isArray(body.items)) throw new Error("The job list could not be read.");
      if (!controller.signal.aborted) setItems(body.items.filter((job) => job.project_id === projectId));
    }).catch((e) => { if (!controller.signal.aborted) { setError(e); setItems(null); } });
    return () => controller.abort();
  }, [api, projectId, tick, eventId]);
  return <><div className="section-heading"><h2>Project jobs</h2><a className="button-link" href={`/jobs/new?project=${encodeURIComponent(projectId)}`}>Submit a job</a></div>
    <Problem error={error} /><button className="secondary" onClick={() => setTick((t) => t + 1)}>Refresh jobs</button>
    {!items && !error && <p role="status">Loading jobs…</p>}
    {items?.length === 0 && <p>No jobs yet. Submit your first training job.</p>}
    <ul className="project-list">{items?.map((job) => <li key={job.job_id}><a href={jobHref(job.job_id)}><strong>{job.job_id}</strong> / {job.spec?.model}</a><p><LiveJobStatus job={job} feedState={feed} /></p></li>)}</ul>
    <JobAlerts feedState={feed} renderJobLink={(id) => <a href={jobHref(id)}>{id}</a>} /></>;
}
