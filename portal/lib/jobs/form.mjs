// Public job-submission contract. Keep values numeric and reject invalid parallelism before POST.
export const JOB_DEFAULTS = { model: "tabular_mlp", epochs: "1", batch_size: "4", learning_rate: "0.05", gpu_count: "0", cpu_cores: "2", memory_gb: "4", strategy: "single", max_runtime_minutes: "10", retry_limit: "2", extras: '{"seed":7,"hidden_size":8}' };
const integer = (value, name, min, max) => {
  if (String(value).trim() === "") throw new Error(`${name} is required.`);
  const n = Number(value);
  if (!Number.isInteger(n) || n < min || n > max) throw new Error(`${name} must be a whole number from ${min} to ${max}.`);
  return n;
};
export function jobSubmission(projectId, datasetId, version, fields) {
  if (!/^project-\d+$/.test(projectId) || !/^dataset-\d+$/.test(datasetId)) throw new Error("Select a project and dataset.");
  if (!/^[a-z0-9_]{1,64}$/.test(fields.model)) throw new Error("Enter a valid model name.");
  const gpu = integer(fields.gpu_count, "GPU count", 0, 8);
  if (!["single", "ddp"].includes(fields.strategy)) throw new Error("Select single or DDP.");
  if (fields.strategy === "ddp" && gpu < 2) throw new Error("DDP needs at least 2 GPUs. Its world size equals the GPU count.");
  const rate = Number(fields.learning_rate);
  if (!Number.isFinite(rate) || rate <= 0 || rate > 10) throw new Error("Learning rate must be greater than 0 and at most 10.");
  let extras;
  try { extras = JSON.parse(fields.extras || "{}"); } catch { throw new Error("Extra hyperparameters must be a JSON object."); }
  if (!extras || Array.isArray(extras) || typeof extras !== "object" || Object.values(extras).some((v) => v === null || !["number", "string", "boolean"].includes(typeof v))) throw new Error("Extra hyperparameters must contain only numbers, strings or booleans.");
  if (["epochs", "batch_size", "learning_rate"].some((key) => key in extras)) throw new Error("Set epochs, batch size and learning rate in their own fields.");
  return { project_id: projectId, dataset_id: datasetId, dataset_version: integer(version, "Dataset version", 1, Number.MAX_SAFE_INTEGER), model: fields.model,
    hyperparameters: { ...extras, epochs: integer(fields.epochs, "Epochs", 1, 1000), batch_size: integer(fields.batch_size, "Batch size", 1, 4096), learning_rate: rate },
    resources: { gpu_count: gpu, cpu_cores: integer(fields.cpu_cores, "CPU cores", 1, 96), memory_gb: integer(fields.memory_gb, "Memory GB", 1, 768) },
    parallelism: { strategy: fields.strategy, world_size: fields.strategy === "ddp" ? gpu : 1 },
    execution: { max_runtime_minutes: integer(fields.max_runtime_minutes, "Time limit", 1, 1440), retry_limit: integer(fields.retry_limit, "Retry limit", 0, 5) } };
}
export const jobHref = (id) => `/jobs/${encodeURIComponent(id)}`;
export const isJobId = (id) => /^job-\d+$/.test(id);
export const canCancel = (status) => ["QUEUED", "SCHEDULED", "RUNNING"].includes(status);

// Preserve an unchanged submission's key across a lost response, page reload or navigation.
// Storage holds only the submitted form and retry key, never authentication tokens.
export function retryKey(spec, storage, makeKey = () => crypto.randomUUID()) {
  const fingerprint = JSON.stringify(spec);
  const name = retryStorageKey(spec);
  try { const old = JSON.parse(storage?.getItem(name) || "null"); if (old?.fingerprint === fingerprint && old.key) return old.key; } catch {}
  const key = makeKey();
  try { storage?.setItem(name, JSON.stringify({ fingerprint, key })); } catch {}
  return key;
}

export const retryStorageKey = (spec) => `cloudtrain:pending-job:${JSON.stringify(spec)}`;

// A read started before cancellation must not replace a newer mutation response.
export function newestJob(current, incoming) {
  if (!current) return incoming;
  if (incoming.job_id !== current.job_id || incoming.project_id !== current.project_id) return current;
  const oldTime = Date.parse(current.updated_at), newTime = Date.parse(incoming.updated_at);
  if (newTime < oldTime || incoming.attempt < current.attempt) return current;
  if (newTime === oldTime && incoming.attempt === current.attempt && !canCancel(current.status) && canCancel(incoming.status)) return current;
  return incoming;
}

export function jobRecord(data, expectedId, expectedProject) {
  if (!data || data.job_id !== expectedId || !/^project-\d+$/.test(data.project_id) || (expectedProject && data.project_id !== expectedProject) || !data.spec || !Array.isArray(data.history) || !["QUEUED", "SCHEDULED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"].includes(data.status)) throw new Error("The job response could not be read or does not match this page.");
  return data;
}
