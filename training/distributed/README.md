# Distributed training and parallelism — `training/distributed/`

| Owners (partners) | Port | Contract |
|---|---|---|
| Ahmed + Abdulla (Student 5) | — (part of the worker) | `contracts/training-job.schema.json` (`parallelism`, `resources`) |

## What it must do
- PyTorch **DistributedDataParallel** (DDP), plugged into Abdullah's training runtime
- **Mandatory benchmark:** 1 GPU vs multi-GPU DDP — speedup, efficiency, throughput, GPU-hours and cost
- CPU data-loading parallelism (several DataLoader workers) and its tuning
- Communication and synchronisation overhead measurements
- The **parallelism selector**: prefer
  - a single worker when the model fits on one GPU and the data is small
  - DDP when throughput is the limit and several GPUs are available
  - model parallelism when the model does not fit on one GPU
  - parallel trials for independent experiments

  weighing GPU availability, memory, model size, dataset size, communication overhead and budget.
- Tensor / pipeline parallelism only on real multi-GPU hardware — **never simulated and presented as real GPU scaling**.

In the job form: `parallelism.strategy` is `single` or `ddp`; for `ddp`, `world_size` equals `resources.gpu_count`.

## Endpoints
None of its own. Runs inside the worker.

## Reads and writes
Same as the worker: MLflow runs and the `artifacts` bucket. Results go in `docs/BENCHMARKS.md`.

## Acceptance test
A real distributed job on 2+ GPUs, with documented scaling compared against a single GPU.
