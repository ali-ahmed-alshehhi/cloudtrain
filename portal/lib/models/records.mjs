const id = (value, kind) => new RegExp(`^${kind}-[0-9]+$`).test(value || "");
const version = value => Number.isSafeInteger(value) && value > 0;
export function modelsOf(body, projectId) {
  if (!Array.isArray(body?.items) || body.items.some(m => !id(m.model_id, "model") || !id(m.project_id, "project") || typeof m.name !== "string" || !version(m.latest_version) || !(m.production_version === null || version(m.production_version)))) throw new Error("The model list could not be read.");
  return body.items.filter(m => m.project_id === projectId);
}
export function versionsOf(body, modelId) {
  if (!id(modelId, "model") || !Array.isArray(body?.items) || body.items.some(v => v.model_id !== modelId || !version(v.version) || typeof v.name !== "string" || typeof v.mlflow_run_id !== "string" || typeof v.artifact_uri !== "string" || !id(v.job_id, "job") || !id(v.dataset_id, "dataset") || !version(v.dataset_version) || !["none", "production", "archived"].includes(v.stage) || !v.metrics || typeof v.metrics !== "object" || Array.isArray(v.metrics) || Object.values(v.metrics).some(n => typeof n !== "number" || !Number.isFinite(n)))) throw new Error("The model versions could not be read or do not match this model.");
  return body.items;
}
export function registration(projectId, name, job, run) {
  const clean = name.trim();
  if (!clean || clean.length > 100) throw new Error("Use a model name of 1–100 characters.");
  if (!id(projectId, "project") || job?.project_id !== projectId || !id(job?.job_id, "job") || job.status !== "SUCCEEDED" || !id(job.spec?.dataset_id, "dataset") || !version(job.spec?.dataset_version)) throw new Error("Choose a successful job from this project.");
  if (typeof run?.runId !== "string" || !run.runId || run.runId.length > 64 || run.status !== "FINISHED" || run.tags?.project_id !== projectId || run.tags?.job_id !== job.job_id) throw new Error("Choose a finished MLflow run for this job.");
  return { project_id: projectId, name: clean, mlflow_run_id: run.runId, job_id: job.job_id, dataset_id: job.spec.dataset_id, dataset_version: job.spec.dataset_version };
}
export function productionOf(body, modelId) {
  if (body?.model_id !== modelId || !version(body.version)) throw new Error("The live-version response does not match this model. Refresh to check its current state.");
  return body;
}
export function predictionOf(body, modelId) {
  productionOf(body, modelId);
  if (!Array.isArray(body.predictions) || !body.predictions.length || body.predictions.some(p => typeof p.label !== "string" || !p.label || typeof p.score !== "number" || !Number.isFinite(p.score) || p.score < 0 || p.score > 1)) throw new Error("The prediction response could not be read.");
  return body;
}
export function predictionForm(modelId, file) {
  if (!id(modelId, "model")) throw new Error("Choose a model with a live version.");
  if (!file || file.size === 0 || !(["image/png", "image/jpeg"].includes(file.type) || (!file.type && /\.(png|jpe?g)$/i.test(file.name)))) throw new Error("Choose a nonempty PNG or JPEG image.");
  const form = new FormData(); form.set("model_id", modelId); form.set("file", file); return form;
}
// Persist only a request fingerprint/key, never a token, so lost responses can be retried safely.
export function registrationKey(spec, storage, makeKey = () => crypto.randomUUID()) {
  const fingerprint = JSON.stringify(spec), slot = `cloudtrain:pending-model:${fingerprint}`;
  try { const old = storage?.getItem(slot); if (old) return { key: old, slot }; } catch {}
  const key = makeKey(); try { storage?.setItem(slot, key); } catch {}
  return { key, slot };
}

export function successfulJobsOf(body, projectId) {
  if (!Array.isArray(body?.items) || body.items.some(j => !id(j?.job_id, "job") || !id(j?.project_id, "project") || typeof j.status !== "string" || !j.spec || typeof j.spec.model !== "string" || !id(j.spec.dataset_id, "dataset") || !version(j.spec.dataset_version))) throw new Error("The training jobs could not be read.");
  return body.items.filter(j => j.project_id === projectId && j.status === "SUCCEEDED");
}
