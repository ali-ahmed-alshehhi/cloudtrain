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

## Status (14 Nov 2026)

| Part | State |
|---|---|
| DDP helpers | Done. Tested with two processes on a CPU. Not yet run on 2 GPUs |
| Benchmark tool | Done. Local runs on 1 GPU, with synthetic images and with real CIFAR-10, in `docs/BENCHMARKS.md` |
| Parallelism selector | Done. Two of its values are assumptions until the cloud benchmark |
| Plugged into the training runtime | Waiting for the runtime (issue #28) |
| Mandatory benchmark, 1 vs 2 GPUs | Waiting for the cloud machine (issue #30) |
| Results for the comparison page | Local result files are ready to build on. The 2-GPU numbers wait for the cloud run (issue #76) |

## What we need from teammates

| From | What we need | Needed by | Our issue |
|---|---|---|---|
| Abdullah (4), training runtime | The runtime calls `ddp.launch` for a `ddp` job: see "Use it in a training script" and the list under it | Wed 18 Nov | #28 |
| Hamda + Fatma (6), infrastructure | One machine with 2 or more GPUs of the same type, with the NVIDIA driver and the NVIDIA container toolkit, and CIFAR-10 on its disk. In `contracts/pricing.yaml` the only type with several GPUs is `g4dn.12xlarge` (4× T4) | Sat 21 Nov | #30 |
| Hamda + Fatma (6), infrastructure | Real prices in `contracts/pricing.yaml`. They are placeholders today, so the cost column of the benchmark stays empty | Tue 24 Nov | #30 |
| Maitha (7), scheduler | A `ddp` job placed on **one** machine that has `resources.gpu_count` GPUs, all of them visible to the container. Our DDP starts all its processes on one machine: it does not span machines | Sat 21 Nov | #30 |

The acceptance test stays open until the machine with 2 GPUs exists. The commands for that run are ready in
`docs/BENCHMARKS.md`, sections 2 and 3.

## What teammates can use today

| For | What | Where |
|---|---|---|
| Abdullah (4) | A training function that already runs as `single` and as `ddp` | `train.py`, and "Use it in a training script" below |
| Maitha (7) | The strategy and the number of GPUs that pay off for a job, with the reason | `selector.py`: `select(Workload(...))` |
| Hilal + Adel (10) | Real result files in the layout the cloud run will produce, to build the comparison page on | `docs/benchmarks/*.json`, and "Result files" below |
| Hamda + Fatma (6) | The exact commands of the cloud benchmark, and what the machine needs | `docs/BENCHMARKS.md`, sections 2 and 3 |

## Files

| File | What it does |
|---|---|
| `ddp.py` | Starts one training process per GPU and gives the training code what it needs: `launch`, `wrap`, `unwrap`, `make_loader`, `worker_context`, `set_epoch` |
| `train.py` | A reference training loop (ResNet-18 on CIFAR-10 or on synthetic images) that runs as `single` or `ddp` and measures itself |
| `benchmark.py` | Runs the comparisons (`scaling`, `workers`) and prints the tables for `docs/BENCHMARKS.md` (`report`) |
| `metrics.py` | Speedup, efficiency, throughput, GPU-hours and cost, from saved results |
| `selector.py` | The parallelism selector: `select(Workload(...))` returns the choice and its reason |

## Run it
PyTorch is not in `training/requirements*.txt` yet, so install it next to the test tools.
`ddp` needs Linux or WSL2: PyTorch for Windows cannot start DDP processes. Run everything from `training/`.

```bash
cd training
python3.11 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt torch==2.9.1 torchvision==0.24.1

# one process, then two DDP processes, on a CPU with a tiny model (a few seconds each)
.venv/bin/python -m distributed.train --model tiny --device cpu --train-size 256 --val-size 64
.venv/bin/python -m distributed.train --model tiny --device cpu --train-size 256 --val-size 64 --strategy ddp --world-size 2

# the benchmarks: every GPU count, then every number of DataLoader workers
.venv/bin/python -m distributed.benchmark scaling --gpus 1 2 --out scaling.json
.venv/bin/python -m distributed.benchmark workers --values 0 2 4 8 --out workers.json
.venv/bin/python -m distributed.benchmark report scaling.json
```

Without `--dataset cifar10 --data-dir <folder>` the tools train on synthetic images, so nothing is downloaded.
The tools never download CIFAR-10 themselves: `<folder>` must already hold `cifar-10-batches-py/`, unpacked
from `cifar-10-python.tar.gz` (MD5 `c58f30108f718f92721af3b95e74349a`, the value torchvision checks).
The exact commands for the cloud benchmark are in `docs/BENCHMARKS.md`.

The selector, in Python:

```python
from distributed.selector import Workload, select

decision = select(
    Workload(
        model_memory_gb=2,
        gpu_memory_gb=16,
        gpus_available=4,
        dataset_images=50_000,
        epochs=100,
        images_per_second=2_500,
    )
)
decision.strategy, decision.world_size, decision.reason  # "ddp", 4, "throughput is the limit: ..."
```

## Use it in a training script
Write the training function once. It then runs as `single` (one process) or as `ddp` (one process per GPU):

```python
from distributed import ddp


def train(ctx, job):  # runs in every process
    model = ddp.wrap(build_model().to(ctx.device), ctx)
    loader = ddp.make_loader(dataset, batch_size, ctx, shuffle=True, num_workers=4)
    for epoch in range(epochs):
        ddp.set_epoch(loader, epoch)
        ...  # the usual training loop
    if ctx.is_main:  # exactly one process logs, evaluates and saves
        save(ddp.unwrap(model))


ddp.launch(train, world_size, args=(job,))  # world_size is parallelism.world_size
```

What the runtime needs to know (issue #28):
- `launch` waits until training ends. If one process fails, it stops the others and raises the error.
- `train` must be a function at the top of a module, and `job` must be picklable: every process is new.
- `batch_size` is per process, so one step uses `batch_size × world_size` samples.
- Build the training DataLoader with `ddp.make_loader`. For a loader of your own, such as one for evaluation,
  pass `multiprocessing_context=ddp.worker_context(num_workers)`. Without it, the workers of a launched
  process are spawned, not forked: on CIFAR-10 that cost 2 seconds per worker (`docs/BENCHMARKS.md`, section 3).
- Log to MLflow and save only when `ctx.is_main`, and save `ddp.unwrap(model)`, not the DDP wrapper.
- The image needs `COPY distributed ./distributed` in `training/Dockerfile`, and `torch` and `torchvision`
  in `training/requirements.txt`.
- DataLoader workers need shared memory: start the container with `--shm-size=2g` or `--ipc=host`.

## Endpoints
None of its own. Runs inside the worker.

## Reads and writes
The helpers read and write nothing themselves. The training function that the runtime passes to `launch`
writes what the worker writes: MLflow runs and the `artifacts` bucket.
The benchmark tool writes one JSON file per benchmark. The files behind `docs/BENCHMARKS.md` are in `docs/benchmarks/`.

### Result files

| Field | Meaning |
|---|---|
| `experiment` | `scaling` or `workers` |
| `machine_type` | The machine type from `contracts/pricing.yaml`, or `null` for a local run |
| `results[]` | One entry per run |
| `results[].strategy`, `.gpus`, `.seed`, `.num_workers`, `.batch_size`, `.epochs` | What the run used |
| `results[].epochs_detail[]` | For each epoch: `seconds`, `images` and `data_wait_seconds` |
| `results[].total_seconds` | The whole run, with start-up and evaluation |
| `results[].accuracy` | On the held-out images after the last epoch, from 0 to 1 |
| `results[].sync_probe` | Step time with and without gradient sharing, or `null` when it was not measured |
| `results[].environment` | GPU, CPU count, and the PyTorch, CUDA and NCCL versions |

Speedup, efficiency, GPU-hours and cost are not stored in the files. `metrics.scaling_rows(results, hourly_usd)`
computes them: it returns one dictionary per GPU count with `run`, `gpus`, `repeats`, `time_per_epoch_s`,
`images_per_second`, `total_seconds`, `accuracy`, `speedup`, `efficiency`, `gpu_hours` and `cost_usd`.
`python -m distributed.benchmark report <file>` prints the same rows as a table.

## Run the tests
```bash
cd training
python3.11 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest                        # the DDP tests are skipped: no PyTorch
.venv/bin/pip install torch==2.9.1 torchvision==0.24.1
.venv/bin/python -m pytest                        # everything; the DDP tests need Linux or WSL2
```

CI installs `requirements-dev.txt` only, so it runs the selector and metrics tests and skips the DDP tests
until PyTorch is added there with the runtime.

## Acceptance test
A real distributed job on 2+ GPUs, with documented scaling compared against a single GPU.
