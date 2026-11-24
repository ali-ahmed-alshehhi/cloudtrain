"use client";
import { useEffect, useMemo, useState } from "react";
import Navigation from "../../app/components/navigation";
import Problem from "../../app/components/problem";
import { createGatewayClient } from "../../app/lib/gateway.mjs";
import { isJobId, canCancel, jobHref, newestJob, jobRecord } from "../../lib/jobs/form.mjs";
import { useAlertFeed } from "../alerts/useAlertFeed";
import { latestJobStatus } from "../../lib/alerts/describe.mjs";
import LiveJobStatus from "../alerts/LiveJobStatus";
import JobAlerts from "../alerts/JobAlerts";
import JobResults from "../experiments/JobResults";
import JobCost from "../usage/JobCost";
import { makeExperimentsApi } from "../../lib/experiments/mlflow.mjs";

export default function JobDetail(props) { return <DetailSession key={`${props.jobId}:${props.gatewayUrl}:${props.devToken}`} {...props} />; }
function DetailSession({ jobId, gatewayUrl, devToken }) {
  const api = useMemo(() => createGatewayClient({ gatewayUrl, getToken: () => devToken }), [gatewayUrl, devToken]);
  const experiments = useMemo(() => makeExperimentsApi({ gatewayUrl, authToken: devToken }), [gatewayUrl, devToken]);
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!isJobId(jobId)) return;
    const controller = new AbortController(); setJob(null); setError(null);
    api.getJob(jobId, controller.signal).then((data) => {
      jobRecord(data, jobId);
      if (!controller.signal.aborted) setJob(data);
    }).catch((e) => { if (!controller.signal.aborted) setError(e); });
    return () => controller.abort();
  }, [api, jobId, tick]);
  return <div className="shell"><Navigation active="jobs" projectId={job?.project_id} /><main>
    <header className="page-header"><div><p className="eyebrow">TRAINING RUN</p><h1>{jobId}</h1><p>Live status, recorded history and metrics for this job.</p></div></header>
    {!devToken && <p className="notice">A signed-in session is required. Portal sign-in integration is pending.</p>}
    <div className="job-actions"><a href={job ? `/jobs?project=${encodeURIComponent(job.project_id)}` : "/jobs"}>Back to jobs</a><button className="secondary" onClick={() => setTick((t) => t + 1)}>Refresh job</button></div>
    {!isJobId(jobId) ? <p role="alert">Invalid job ID.</p> : <><Problem error={error} />{!job && !error && <p role="status">Loading job…</p>}{job && <LoadedJob key={tick} initial={job} api={api} experiments={experiments} />}</>}
  </main></div>;
}
function LoadedJob({ initial, api, experiments }) {
  const [job, setJob] = useState(initial);
  const [readError, setReadError] = useState(null);
  const [cancelError, setCancelError] = useState(null);
  const [cancelling, setCancelling] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [tick, setTick] = useState(0);
  const feed = useAlertFeed({ fetchEvents: api.fetchEvents, projectId: initial.project_id });
  const events = feed?.events?.filter((e) => e.job_id === initial.job_id) || [];
  const eventId = events.at(-1)?.event_id;
  useEffect(() => {
    if (!eventId && tick === 0) return;
    const controller = new AbortController();
    api.getJob(initial.job_id, controller.signal).then((data) => {
      jobRecord(data, initial.job_id, initial.project_id);
      if (!controller.signal.aborted) { setJob((current) => newestJob(current, data)); setReadError(null); }
    }).catch((e) => { if (!controller.signal.aborted) setReadError(e); });
    return () => controller.abort();
  }, [api, initial.job_id, initial.project_id, eventId, tick]);
  const live = latestJobStatus(job, events);
  async function cancel() {
    if (cancelling) return;
    setCancelling(true); setCancelError(null);
    try { const data = jobRecord(await api.cancelJob(job.job_id), job.job_id, job.project_id); setJob((current) => newestJob(current, data)); setConfirming(false); }
    catch (e) { setCancelError(e); setTick((t) => t + 1); }
    finally { setCancelling(false); }
  }
  if (readError) return <section className="panel"><Problem error={readError} /><p>Refresh this job to load its current data.</p><button onClick={() => setTick((t) => t + 1)}>Retry job</button></section>;
  const jobFeed = feed ? { ...feed, events, newEvents: feed.newEvents?.filter((e) => e.job_id === job.job_id) || [] } : null;
  return <><section className="panel"><div className="section-heading"><h2>Job status</h2><LiveJobStatus job={job} feedState={jobFeed} /></div>
    <p>Project {job.project_id}. Dataset {job.spec.dataset_id}, version {job.spec.dataset_version}. Model {job.spec.model}.</p>
    <p>Strategy {job.spec.parallelism?.strategy}, world size {job.spec.parallelism?.world_size}. Attempt {job.attempt}.</p>
    {canCancel(live.status) && <div className="job-actions">{!confirming ? <button className="secondary" onClick={() => setConfirming(true)}>Cancel job</button> : <><p>Cancel this training job?</p><button disabled={cancelling} onClick={cancel}>{cancelling ? "Cancelling…" : "Confirm cancellation"}</button><button className="secondary" disabled={cancelling} onClick={() => setConfirming(false)}>Keep running</button></>}</div>}
    <Problem error={cancelError} /><JobCost job={job} />
  </section><section className="panel"><h2>Status history</h2><ol className="history" data-testid="job-history">{job.history?.map((entry, index) => <li key={`${entry.at}:${index}`}><strong>{entry.status}</strong><time dateTime={entry.at}>{new Date(entry.at).toLocaleString()}</time>{entry.reason && <p>{entry.reason}</p>}</li>)}</ol></section>
  <section className="panel"><JobAlerts feedState={jobFeed} title="This job’s alerts" renderJobLink={(id) => <a href={jobHref(id)}>{id}</a>} /></section>
  <section className="panel" style={{ overflowX: "auto" }}><JobResults job={job} api={experiments} liveStatus={live.status} /></section></>;
}
