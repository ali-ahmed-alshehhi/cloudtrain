"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import WorkspacePage from "../pages/WorkspacePage";
import { createGatewayClient } from "../../app/lib/gateway.mjs";
import Problem from "../../app/components/problem";
import { JOB_DEFAULTS, jobSubmission, jobHref, retryKey, retryStorageKey } from "../../lib/jobs/form.mjs";

export default function SubmitView({ gatewayUrl, devToken, requestedProject }) {
  const api = useMemo(() => createGatewayClient({ gatewayUrl, getToken: () => devToken }), [gatewayUrl, devToken]);
  const [locked, setLocked] = useState(false);
  return <WorkspacePage gatewayUrl={gatewayUrl} devToken={devToken} requestedProject={requestedProject} active="jobs" pagePath="/jobs/new" eyebrow="NEW TRAINING RUN" title="Submit a job" intro="Choose the data and training settings. The server validates and queues your job." projectLocked={locked}>
    {(id) => <JobForm key={`${id}:${devToken}`} api={api} projectId={id} onBusy={setLocked} />}
  </WorkspacePage>;
}
const NUMBERS = [["epochs", "Epochs", 1, 1000], ["batch_size", "Batch size", 1, 4096], ["learning_rate", "Learning rate", 0.000000001, 10], ["gpu_count", "GPU count", 0, 8], ["cpu_cores", "CPU cores", 1, 96], ["memory_gb", "Memory (GB)", 1, 768], ["max_runtime_minutes", "Time limit (minutes)", 1, 1440], ["retry_limit", "Retry limit", 0, 5]];
function JobForm({ api, projectId, onBusy }) {
  const [datasets, setDatasets] = useState(null);
  const [datasetId, setDatasetId] = useState("");
  const [version, setVersion] = useState(1);
  const [metadata, setMetadata] = useState(null);
  const [fields, setFields] = useState({ ...JOB_DEFAULTS });
  const [loadError, setLoadError] = useState(null);
  const [versionError, setVersionError] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [tick, setTick] = useState(0);
  const saving = useRef(false);
  const retry = useRef(null);
  const dataset = datasets?.find((d) => d.dataset_id === datasetId);
  useEffect(() => {
    const controller = new AbortController(); setLoadError(null); setDatasets(null);
    api.listDatasets(projectId, controller.signal).then((body) => {
      if (!Array.isArray(body.items)) throw new Error("The dataset list could not be read.");
      if (!controller.signal.aborted) setDatasets(body.items.filter((d) => d.project_id === projectId));
    }).catch((e) => { if (!controller.signal.aborted) setLoadError(e); });
    return () => controller.abort();
  }, [api, projectId, tick]);
  useEffect(() => {
    setMetadata(null); setVersionError(null); if (!datasetId) return;
    const controller = new AbortController();
    api.getDatasetVersion(datasetId, version, controller.signal).then((data) => {
      if (data.dataset_id !== datasetId || data.version !== version) throw new Error("The version response does not match your selection.");
      if (!controller.signal.aborted) setMetadata({ datasetId, version, data });
    }).catch((e) => { if (!controller.signal.aborted) setVersionError(e); });
    return () => controller.abort();
  }, [api, datasetId, version, tick]);
  const versionReady = metadata?.datasetId === datasetId && metadata?.version === version;
  function field(key, value) { setFields((old) => ({ ...old, [key]: value })); }
  async function submit(event) {
    event.preventDefault(); if (saving.current) return; setError(null);
    try {
      if (!versionReady) throw new Error("Wait for the selected dataset version to load.");
      const spec = jobSubmission(projectId, datasetId, version, fields);
      const fingerprint = JSON.stringify(spec);
      if (retry.current?.fingerprint !== fingerprint) {
        let storage; try { storage = window.sessionStorage; } catch {}
        retry.current = { fingerprint, key: retryKey(spec, storage) };
      }
      saving.current = true; setBusy(true); onBusy(true);
      const created = await api.submitJob(spec, retry.current.key);
      if (!/^job-\d+$/.test(created.job_id)) throw new Error("The accepted job response could not be read. Retry this unchanged form safely.");
      try { sessionStorage.removeItem(retryStorageKey(spec)); } catch {}
      window.location.assign(jobHref(created.job_id));
    } catch (e) { setError(e); } finally { saving.current = false; setBusy(false); onBusy(false); }
  }
  return <><Problem error={loadError} />{loadError && <button onClick={() => setTick((t) => t + 1)}>Retry datasets</button>}
    {!datasets && !loadError && <p role="status">Loading datasets…</p>}
    {datasets?.length === 0 && <p>No datasets in this project. <a href="/#datasets">Upload a dataset on the Projects page</a>, then return here.</p>}
    {datasets?.length > 0 && <form onSubmit={submit}><fieldset disabled={busy}>
      <label htmlFor="job-dataset">Dataset</label><select id="job-dataset" required value={datasetId} onChange={(e) => { const id = e.target.value; setDatasetId(id); setVersion(datasets.find((d) => d.dataset_id === id)?.latest_version || 1); setMetadata(null); }}><option value="">Choose a dataset</option>{datasets.map((d) => <option key={d.dataset_id} value={d.dataset_id}>{d.name} ({d.format})</option>)}</select>
      {dataset && <><label htmlFor="job-version">Dataset version</label><select id="job-version" value={version} onChange={(e) => { setVersion(Number(e.target.value)); setMetadata(null); }}>{Array.from({ length: dataset.latest_version }, (_, i) => <option key={i + 1} value={i + 1}>Version {i + 1}</option>)}</select>
        <Problem error={versionError} />{versionError && <button type="button" onClick={() => setTick((t) => t + 1)}>Retry version</button>}
        {!versionReady && !versionError && <p role="status">Loading version…</p>}
        {versionReady && <p className="notice" data-testid="job-dataset-version">{datasetId}, version {version}: {metadata.data.size_bytes} bytes. SHA-256: {metadata.data.checksum_sha256}</p>}</>}
      <label htmlFor="job-model">Model</label><select id="job-model" value={fields.model} onChange={(e) => field("model", e.target.value)}><option value="tabular_mlp">Tabular MLP (numeric CSV)</option><option value="resnet18">ResNet-18 (CIFAR-10 image archive)</option></select>
      <p className="muted">For a laptop demo, use numeric CSV with target column diagnosis and tabular_mlp. Data must match the model. GPU requests on the emulator do not prove real GPU execution.</p>
      <label htmlFor="job-strategy">Strategy</label><select id="job-strategy" value={fields.strategy} onChange={(e) => field("strategy", e.target.value)}><option value="single">Single process</option><option value="ddp">Distributed (DDP)</option></select>
      <p>World size: {fields.strategy === "single" ? 1 : fields.gpu_count}. DDP requires at least 2 GPUs and uses the same world size as GPU count.</p>
      <div className="field-grid">{NUMBERS.map(([key, label, min, max]) => <div key={key}><label htmlFor={`job-${key}`}>{label}</label><input id={`job-${key}`} type="number" required min={min} max={max} step={key === "learning_rate" ? "any" : "1"} value={fields[key]} onChange={(e) => field(key, e.target.value)} /></div>)}</div>
      <label htmlFor="job-extra">Extra hyperparameters (JSON object)</label><textarea id="job-extra" rows={3} value={fields.extras} onChange={(e) => field("extras", e.target.value)} /><p className="muted">Tabular defaults include seed 7 and hidden_size 8. You can set target_column for your CSV. Use only numbers, strings or booleans.</p>
      <button type="submit" disabled={!versionReady}>{busy ? "Submitting job…" : "Submit training job"}</button>
      {busy && <p role="status">Submitting job. Project selection is locked until the request finishes.</p>}
    </fieldset><Problem error={error} /></form>}</>;
}
