"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import WorkspacePage from "../pages/WorkspacePage";
import Problem from "../../app/components/problem";
import { createGatewayClient } from "../../app/lib/gateway.mjs";
import { modelsOf, predictionForm, predictionOf } from "../../lib/models/records.mjs";

export default function PredictView({ gatewayUrl, devToken, requestedProject }) {
  const api = useMemo(() => createGatewayClient({ gatewayUrl, getToken: () => devToken }), [gatewayUrl, devToken]);
  const [locked, setLocked] = useState(false);
  return <WorkspacePage {...{ gatewayUrl, devToken, requestedProject }} active="predict" eyebrow="LIVE INFERENCE" title="Try a prediction" intro="Send an image to a live model and see the labels it returns." projectLocked={locked}>
    {id => <PredictionForm key={`${id}:${devToken}`} api={api} projectId={id} onBusy={setLocked} />}
  </WorkspacePage>;
}
function PredictionForm({ api, projectId, onBusy }) {
  const [models, setModels] = useState(null), [modelId, setModelId] = useState(""), [file, setFile] = useState(null);
  const [answer, setAnswer] = useState(null), [error, setError] = useState(null), [tick, setTick] = useState(0), [busy, setBusy] = useState(false);
  const pending = useRef(false);
  useEffect(() => {
    const controller = new AbortController(); setModels(null); setAnswer(null); setError(null);
    api.listModels(projectId, controller.signal).then(body => {
      const live = modelsOf(body, projectId).filter(m => m.production_version !== null);
      if (!controller.signal.aborted) { setModels(live); setModelId(old => live.some(m => m.model_id === old) ? old : live[0]?.model_id || ""); }
    }).catch(e => { if (!controller.signal.aborted) setError(e); });
    return () => controller.abort();
  }, [api, projectId, tick]);
  async function submit(event) {
    event.preventDefault(); if (pending.current) return; setAnswer(null); setError(null);
    try {
      const form = predictionForm(modelId, file); pending.current = true; setBusy(true); onBusy(true);
      setAnswer(predictionOf(await api.predict(form), modelId));
    } catch (e) { setError(e); } finally { pending.current = false; setBusy(false); onBusy(false); }
  }
  return <><div className="section-heading"><h2>Predict from an image</h2><button className="secondary" disabled={busy} onClick={() => setTick(t => t + 1)}>Refresh live models</button></div>
    <p className="muted">PNG or JPEG. The returned version identifies the model that actually answered; another user may promote a new version while you work.</p>
    <Problem error={error} />{!models && !error && <p role="status">Loading live models…</p>}
    {models?.length === 0 && <p>No live models in this project. <a href={`/models?project=${encodeURIComponent(projectId)}`}>Register and promote an image model first.</a></p>}
    {models?.length > 0 && <form onSubmit={submit}><fieldset disabled={busy}>
      <label htmlFor="prediction-model">Live model</label><select id="prediction-model" value={modelId} onChange={e => { setModelId(e.target.value); setAnswer(null); setError(null); }}>{models.map(m => <option key={m.model_id} value={m.model_id}>{m.name} · version {m.production_version} ({m.model_id})</option>)}</select>
      <label htmlFor="prediction-file">Image</label><input id="prediction-file" type="file" accept="image/png,image/jpeg,.png,.jpg,.jpeg" required onChange={e => { setFile(e.target.files?.[0] || null); setAnswer(null); setError(null); }} />
      <div className="job-actions"><button type="submit" disabled={!file}>{busy ? "Predicting…" : "Get prediction"}</button></div>
    </fieldset></form>}
    {answer && <section data-testid="prediction-result"><h3>Prediction from {answer.model_id}, version {answer.version}</h3><p>Image: {file?.name}</p><ul className="project-list">{answer.predictions.map((p, i) => <li key={`${i}:${p.label}`} className="model-version"><strong>{p.label}</strong><p>Score: {(p.score * 100).toFixed(2)}%</p></li>)}</ul></section>}
  </>;
}
