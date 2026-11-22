// FIXTURE — made-up runs, NOT real GPU measurements. Never show them as real.
//
// MLflow runs (REST shape, as in mlflow.fixture.mjs) of one workload on 1 GPU and on 2 GPUs with DDP,
// 2 seeds each, plus the per-epoch histories the comparison needs. The numbers are invented and round so
// the expected speedup is easy to check by hand; the real ones come from Ahmed + Abdulla (docs/BENCHMARKS.md).

const tag = (key, value) => ({ key, value: String(value) });
const param = (key, value) => ({ key, value: String(value) });

export function comparisonRun({ runId, jobId, gpus, strategy = gpus === 1 ? "single" : "ddp", accuracy = 0.74,
  start = 1795000000000, totalSeconds = 30, epochs = 3, batch = 128, model = "resnet18", project = "project-01",
  status = "FINISHED", resultLabel = "FIXTURE, not a real run" }) {
  return {
    info: { run_id: runId, run_name: `${jobId}-attempt`, experiment_id: "1", status, start_time: start, end_time: start + totalSeconds * 1000 },
    data: {
      metrics: [{ key: "final_accuracy", value: accuracy, step: 0, timestamp: start }],
      params: [param("model", model), param("dataset_id", "dataset-1"), param("dataset_version", 1), param("epochs", epochs),
        param("batch_size", batch), param("learning_rate", 0.05), param("strategy", strategy), param("world_size", gpus)],
      tags: [tag("job_id", jobId), tag("project_id", project), tag("strategy", strategy), tag("world_size", gpus), tag("model", model),
        ...(resultLabel === null ? [] : [tag("result_label", resultLabel)])],
    },
  };
}

/** Per-epoch history in MLflow's get-history shape. */
export function history(key, values) {
  return { metrics: values.map((value, i) => ({ key, value, step: i + 1, timestamp: 1795000000000 + i })) };
}

// 1 GPU: warm-up epoch 3.0 s, then 2.0 s per epoch, 50,000 images per epoch.
// 2 GPUs (DDP): warm-up 2.4 s, then 1.25 s per epoch. Expected speedup 2.0 / 1.25 = 1.6x, efficiency 80%.
export const FIXTURE_COMPARISON = {
  runs: [
    comparisonRun({ runId: "r-1gpu-a", jobId: "job-11", gpus: 1, totalSeconds: 30, accuracy: 0.74 }),
    comparisonRun({ runId: "r-1gpu-b", jobId: "job-12", gpus: 1, totalSeconds: 32, accuracy: 0.76 }),
    comparisonRun({ runId: "r-2gpu-a", jobId: "job-21", gpus: 2, totalSeconds: 20, accuracy: 0.73 }),
    comparisonRun({ runId: "r-2gpu-b", jobId: "job-22", gpus: 2, totalSeconds: 22, accuracy: 0.75 }),
  ],
  seconds: {
    "r-1gpu-a": [3.0, 2.0, 2.0],
    "r-1gpu-b": [3.2, 1.9, 2.1],
    "r-2gpu-a": [2.4, 1.25, 1.25],
    "r-2gpu-b": [2.6, 1.2, 1.3],
  },
  images: [50000, 50000, 50000],
  jobs: {
    "job-11": { gpus: 1, gpu_hours: 0.0083, cost: 0.0044 },
    "job-12": { gpus: 1, gpu_hours: 0.0089, cost: 0.0047 },
    "job-21": { gpus: 2, gpu_hours: 0.0111, cost: 0.0217 },
    "job-22": { gpus: 2, gpu_hours: 0.0122, cost: 0.0239 },
  },
};
