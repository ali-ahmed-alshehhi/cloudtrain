"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import WorkspacePage from "../pages/WorkspacePage";
import Problem from "../../app/components/problem";
import { createGatewayClient } from "../../app/lib/gateway.mjs";
import { makeExperimentsApi, loadJobResults, DEFAULT_EXPERIMENT } from "../../lib/experiments/mlflow.mjs";
import { modelsOf, versionsOf, registration, productionOf, registrationKey, successfulJobsOf } from "../../lib/models/records.mjs";

export default function ModelsView({ gatewayUrl, devToken, requestedProject }) {
  const api = useMemo(() => createGatewayClient({ gatewayUrl, getToken: () => devToken }), [gatewayUrl, devToken]);
  const experiments = useMemo(() => makeExperimentsApi({ gatewayUrl, authToken: devToken }), [gatewayUrl, devToken]);
  const [locked, setLocked] = useState(false);
  return <WorkspacePage {...{ gatewayUrl, devToken, requestedProject }} active="models" eyebrow="MODEL REGISTRY" title="Models" intro="Register a completed run, review its versions and choose which version serves predictions." projectLocked={locked}>
    {id => <ProjectModels key={`${id}:${devToken}`} api={api} experiments={experiments} projectId={id} onBusy={setLocked} />}
  </WorkspacePage>;
}
function ProjectModels({ api, experiments, projectId, onBusy }) {
  const [models, setModels] = useState(null), [modelId, setModelId] = useState("");
  const [error, setError] = useState(null), [tick, setTick] = useState(0), [busy, setBusy] = useState(false);
  useEffect(() => {
    const controller = new AbortController(); setModels(null); setError(null);
    api.listModels(projectId, controller.signal).then(body => {
      const items = modelsOf(body, projectId); if (controller.signal.aborted) return;
      setModels(items); setModelId(old => items.some(m => m.model_id === old) ? old : items[0]?.model_id || "");
    }).catch(e => { if (!controller.signal.aborted) setError(e); });
    return () => controller.abort();
  }, [api, projectId, tick]);
  function lock(value) { setBusy(value); onBusy(value); }
  function refresh() { setTick(t => t + 1); }
  return <><div className="section-heading"><h2>Registered models</h2><button className="secondary" disabled={busy} onClick={refresh}>Refresh models</button></div>
    <Problem error={error} />{!models && !error && <p role="status">Loading models…</p>}
    {models?.length === 0 && <p>No registered models yet. Register a successful training run below.</p>}
    {models?.length > 0 && <><label htmlFor="registry-model">Registered model</label><select id="registry-model" disabled={busy} value={modelId} onChange={e => setModelId(e.target.value)}>{models.map(m => <option key={m.model_id} value={m.model_id}>{m.name} ({m.model_id})</option>)}</select>
      <ModelVersions key={modelId} api={api} model={models.find(m => m.model_id === modelId)} busy={busy} onBusy={lock} onChanged={refresh} /></>}
    <RegisterForm api={api} experiments={experiments} projectId={projectId} busy={busy} onBusy={lock} onRegistered={refresh} />
  </>;
}
function ModelVersions({ api, model, busy, onBusy, onChanged }) {
  const [items, setItems] = useState(null), [error, setError] = useState(null), [action, setAction] = useState(null);
  const pending = useRef(false);
  useEffect(() => {
    const controller = new AbortController();
    api.listModelVersions(model.model_id, controller.signal).then(body => { const rows = versionsOf(body, model.model_id); if (!controller.signal.aborted) setItems(rows); }).catch(e => { if (!controller.signal.aborted) { setItems(null); setError(e); } });
    return () => controller.abort();
  }, [api, model.model_id, model.production_version]);
  async function change() {
    if (!action || pending.current) return;
    pending.current = true; onBusy(true); setError(null);
    try {
      const answer = action.kind === "promote" ? await api.promoteModel(model.model_id, action.version) : await api.rollbackModel(model.model_id);
      productionOf(answer, model.model_id);
      setItems(null); onChanged();
    } catch (e) { setError(e); }
    finally { setAction(null); pending.current = false; onBusy(false); }
  }
  return <div className="model-versions"><p>Live version: <strong>{model.production_version ? `Version ${model.production_version}` : "Not deployed"}</strong></p>
    <p className="muted">Promotion changes live predictions after the server checks the candidate. A failed health check keeps the previous version live.</p>
    <Problem error={error} />{!items && !error && <p role="status">Loading versions…</p>}
    <ul className="project-list">{items?.map(v => <li key={v.version} className="model-version"><h3>Version {v.version} · {v.stage}</h3>
      <p><a href={`/jobs/${encodeURIComponent(v.job_id)}`}>{v.job_id}</a> · {v.dataset_id}, version {v.dataset_version}</p>
      <dl className="metadata"><dt>MLflow run</dt><dd>{v.mlflow_run_id}</dd><dt>Artifact</dt><dd>{v.artifact_uri}</dd></dl>
      <dl className="model-metrics">{Object.entries(v.metrics).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value.toLocaleString(undefined, { maximumFractionDigits: 5 })}</dd></div>)}</dl>
      {v.stage !== "production" && <button disabled={busy} onClick={() => setAction({ kind: "promote", version: v.version })}>Promote version {v.version}</button>}
    </li>)}</ul>
    {model.production_version && <div className="job-actions"><button className="secondary" disabled={busy} onClick={() => setAction({ kind: "rollback" })}>Roll back live version</button></div>}
    {action && <div className="notice" role="group" aria-label="Confirm deployment"><p>{action.kind === "promote" ? `Make version ${action.version} of ${model.name} live?` : `Restore the previous live version of ${model.name}? The server checks whether one exists.`}</p><div className="job-actions"><button disabled={busy} onClick={change}>{busy ? "Updating live version…" : "Confirm deployment"}</button><button className="secondary" disabled={busy} onClick={() => setAction(null)}>Keep current version</button></div></div>}
  </div>;
}
function RegisterForm({ api, experiments, projectId, busy, onBusy, onRegistered }) {
  const [jobs, setJobs] = useState(null), [jobId, setJobId] = useState(""), [name, setName] = useState("");
  const [experimentName, setExperimentName] = useState(DEFAULT_EXPERIMENT);
  const [runs, setRuns] = useState(null), [runId, setRunId] = useState(""), [error, setError] = useState(null), [notice, setNotice] = useState("");
  const [tick, setTick] = useState(0); const pending = useRef(false), retry = useRef(null);
  const job = jobs?.find(j => j.job_id === jobId);
  useEffect(() => {
    const controller = new AbortController(); setError(null); setJobs(null);
    api.listJobs(projectId, controller.signal).then(body => {
      const successful = successfulJobsOf(body, projectId);
      if (!controller.signal.aborted) setJobs(successful);
    }).catch(e => { if (!controller.signal.aborted) setError(e); });
    return () => controller.abort();
  }, [api, projectId, tick]);
  useEffect(() => {
    let active = true; setRuns(null); setRunId(""); if (!job) return;
    if (!experimentName.trim()) { setRuns([]); return; }
    loadJobResults({ api: experiments, job, experimentName: experimentName.trim() }).then(result => {
      if (!active) return;
      if (!["ready", "none"].includes(result.state)) { setError(new Error(result.error?.message || "MLflow runs could not be loaded. Refresh and try again.")); return; }
      const finished = result.runs.filter(r => r.status === "FINISHED"); setRuns(finished); setRunId(finished[0]?.runId || "");
    });
    return () => { active = false; };
  }, [experiments, job, experimentName]);
  async function submit(event) {
    event.preventDefault(); if (pending.current) return; setError(null); setNotice("");
    try {
      const spec = registration(projectId, name, job, runs?.find(r => r.runId === runId));
      const fingerprint = JSON.stringify(spec);
      if (retry.current?.fingerprint !== fingerprint) { let storage; try { storage = sessionStorage; } catch {} retry.current = { fingerprint, ...registrationKey(spec, storage) }; }
      pending.current = true; onBusy(true);
      const answer = await api.registerModel(spec, retry.current.key);
      versionsOf({ items: [answer] }, answer.model_id);
      if (answer.job_id !== spec.job_id || answer.mlflow_run_id !== spec.mlflow_run_id || answer.dataset_id !== spec.dataset_id || answer.dataset_version !== spec.dataset_version) throw new Error("The registration response does not match this run. Retry the unchanged form safely.");
      try { sessionStorage.removeItem(retry.current.slot); } catch {} retry.current = null;
      setNotice(`Registered ${answer.name}, version ${answer.version}.`); onRegistered();
    } catch (e) { setError(e); } finally { pending.current = false; onBusy(false); }
  }
  return <section className="registration"><h2>Register a training run</h2><p className="muted">Use the same model name to add a version. Lineage comes from the selected job. Image prediction requires an image-compatible model; the tabular MLP can be registered but cannot serve images.</p>
    <Problem error={error} />{notice && <p className="success" role="status">{notice}</p>}
    <button className="secondary" disabled={busy} onClick={() => { setJobId(""); setRuns(null); setTick(t => t + 1); }}>Refresh successful jobs</button>
    {!jobs && !error && <p role="status">Loading successful jobs…</p>}
    {jobs?.length === 0 && <p>No successful jobs yet. <a href={`/jobs?project=${encodeURIComponent(projectId)}`}>Run a training job first.</a></p>}
    {jobs?.length > 0 && <form onSubmit={submit}><fieldset disabled={busy}><label htmlFor="model-name">Model name</label><input id="model-name" required maxLength={100} value={name} onChange={e => setName(e.target.value)} />
      <label htmlFor="registration-job">Successful training job</label><select id="registration-job" required value={jobId} onChange={e => { setJobId(e.target.value); setRuns(null); setRunId(""); setError(null); setNotice(""); }}><option value="">Choose a job</option>{jobs.map(j => <option key={j.job_id} value={j.job_id}>{j.job_id} · {j.spec?.model}</option>)}</select>
      {job && <><p>{job.spec.dataset_id}, version {job.spec.dataset_version}</p><label htmlFor="registration-experiment">MLflow experiment</label><input id="registration-experiment" required value={experimentName} onChange={e => { setExperimentName(e.target.value); setRuns(null); setRunId(""); setError(null); }} />{!runs && !error && <p role="status">Loading MLflow runs…</p>}{runs?.length === 0 && <p>No finished MLflow runs are available for this job.</p>}
      {runs?.length > 0 && <><label htmlFor="registration-run">Finished MLflow run</label><select id="registration-run" value={runId} onChange={e => setRunId(e.target.value)}>{runs.map(r => <option key={r.runId} value={r.runId}>{r.runId}</option>)}</select></>}</>}
      <div className="job-actions"><button type="submit" disabled={!runId}>{busy ? "Registering…" : "Register model version"}</button></div>
    </fieldset></form>}
  </section>;
}
