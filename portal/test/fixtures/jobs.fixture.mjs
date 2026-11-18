// FIXTURE — made-up jobs, NOT real usage or cost. Never show them as real.
//
// Shaped like the contract's Job (contracts/openapi/job-service.yaml, checked by test/usage.test.mjs).
// Costs follow the real hourly prices of #111 (g4dn.xlarge 0.526, g4dn.12xlarge 3.912) so the numbers
// look sensible, but no job here ever ran.

export function fixtureJob(n, overrides = {}) {
  const { resources, ...rest } = overrides;
  return {
    job_id: `job-${n}`,
    project_id: "project-01",
    status: "SUCCEEDED",
    spec: {
      project_id: "project-01",
      dataset_id: "dataset-1",
      dataset_version: 1,
      model: "resnet18",
      hyperparameters: { epochs: 3 },
      resources: { gpu_count: 1, ...resources },
      parallelism: { strategy: "single", world_size: 1 },
      execution: { max_retries: 1 },
    },
    machine_type: "g4dn.xlarge",
    attempt: 1,
    created_at: `2026-11-20T09:${String(n).padStart(2, "0")}:00Z`,
    updated_at: "2026-11-20T10:00:00Z",
    started_at: "2026-11-20T09:30:00Z",
    finished_at: "2026-11-20T10:00:00Z",
    gpu_hours: 0.5,
    estimated_cost_usd: 0.263,
    history: [],
    ...rest,
  };
}

export const FIXTURE_PROJECT_JOBS = [
  fixtureJob(1), // finished, 0.5 GPU-hours, $0.263
  fixtureJob(2, {
    // DDP on 4 GPUs, retried once: both attempts count
    machine_type: "g4dn.12xlarge",
    resources: { gpu_count: 4 },
    attempt: 2,
    gpu_hours: 4,
    estimated_cost_usd: 3.912,
  }),
  fixtureJob(3, { status: "RUNNING", finished_at: null, gpu_hours: 0.25, estimated_cost_usd: 0.1315 }),
  fixtureJob(4, {
    status: "QUEUED",
    machine_type: null,
    started_at: null,
    finished_at: null,
    gpu_hours: 0,
    estimated_cost_usd: 0,
  }),
  fixtureJob(5, { machine_type: "p5.48xlarge", gpu_hours: 8, estimated_cost_usd: null }), // price unknown
  fixtureJob(6, {
    status: "SUCCEEDED",
    machine_type: "local-cpu",
    resources: { gpu_count: 0 },
    gpu_hours: 0,
    estimated_cost_usd: 0, // really free
  }),
];
