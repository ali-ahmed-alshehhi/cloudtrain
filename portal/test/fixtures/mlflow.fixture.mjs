// FIXTURE — made-up MLflow answers, NOT real training or GPU results. Never show them as real.
//
// Shaped like MLflow 3.x REST answers (api/2.0/mlflow: experiments/get-by-name, runs/search,
// metrics/get-history), with the tags and metric names Abdullah's training worker logs
// (training/app/tracking.py and runtime.py on abdullah/training-runtime).

const tag = (key, value) => ({ key, value: String(value) });
const metric = (key, value, step = 0) => ({ key, value, timestamp: 1795000000000 + step, step });

export const FIXTURE_EXPERIMENT = {
  experiment: { experiment_id: "1", name: "cloudtrain", lifecycle_stage: "active" },
};

export function fixtureRun({
  runId = "run-fixture-a",
  jobId = "job-104",
  projectId = "project-01",
  status = "FINISHED",
  start = 1795000000000,
  end = 1795000200000, // 200 s later
  strategy = "single",
  worldSize = 1,
  metrics = [
    metric("accuracy", 0.912, 3),
    metric("f1", 0.905, 3),
    metric("validation_loss", 0.2841, 3),
    metric("train_loss", 0.2512, 3),
    metric("final_accuracy", 0.912),
    metric("final_f1", 0.905),
    metric("final_validation_loss", 0.2841),
    metric("final_train_loss", 0.2512),
  ],
} = {}) {
  return {
    info: {
      run_id: runId,
      run_name: `${jobId}-attempt`,
      experiment_id: "1",
      status,
      start_time: start,
      end_time: end,
      lifecycle_stage: "active",
    },
    data: {
      metrics,
      params: [{ key: "epochs", value: "3" }, { key: "model", value: "resnet18" }],
      tags: [
        tag("job_id", jobId),
        tag("project_id", projectId),
        tag("strategy", strategy),
        tag("world_size", worldSize),
        tag("model", "resnet18"),
        tag("mlflow.runName", `${jobId}-attempt`),
      ],
    },
  };
}

// Attempt 1 failed after one epoch; attempt 2 finished.
export const FIXTURE_TWO_ATTEMPTS = [
  fixtureRun(), // newest
  fixtureRun({
    runId: "run-fixture-old",
    status: "FAILED",
    start: 1794990000000,
    end: 1794990060000,
    metrics: [metric("accuracy", 0.61, 1), metric("train_loss", 1.12, 1)],
  }),
];

export const FIXTURE_HISTORY = {
  accuracy: [metric("accuracy", 0.71, 1), metric("accuracy", 0.86, 2), metric("accuracy", 0.912, 3)],
  validation_loss: [metric("validation_loss", 0.81, 1), metric("validation_loss", 0.41, 2), metric("validation_loss", 0.2841, 3)],
  train_loss: [metric("train_loss", 1.02, 1), metric("train_loss", 0.44, 2), metric("train_loss", 0.2512, 3)],
};

// What the gateway sends for MLflow errors (gateway/app/proxy.py mlflow_error).
export function fixtureGatewayError(code, message) {
  return { error: { code, message, request_id: "req-fixture" } };
}
