# Benchmarks: training and distributed parallelism

**Owners:** Ahmed + Abdulla (Student 5). **Real** measurements only.
Tensor and pipeline parallelism must never be simulated and presented as real GPU scaling.

> **Status on 14 Nov 2026: the mandatory benchmark on 2 GPUs has not run yet.** It needs the team's cloud
> machine with 2 or more GPUs (issue #30). The numbers below come from **local runs** on a workstation
> with one GPU: on real CIFAR-10 images, and on synthetic images. They show that the tools work and give
> first results for sections 3, 4 and 6. Everything that still waits for the cloud run is marked
> **pending**.

Every number here comes from a result file in [`docs/benchmarks/`](benchmarks/). To print the tables of a
file again, run `python -m distributed.benchmark report ../docs/benchmarks/<file>` from `training/`.

## 1. Setup

| | Local runs (done) | Cloud benchmark (pending) |
|---|---|---|
| Model | ResNet-18 from torchvision, 10 classes, trained from scratch | The same |
| Dataset | CIFAR-10: 50,000 images for training, 10,000 for testing. Also synthetic images of the same shape and number, for runs with nothing to download | CIFAR-10 |
| Hardware | 1× NVIDIA GeForce RTX 5090, 16 CPU threads | A machine type from `contracts/pricing.yaml` with 2 or more GPUs |
| Software | PyTorch 2.9.1 with CUDA 12.8, Python 3.12.3, Linux 6.18 under WSL2 | Saved by the tool in every result file, with the NCCL version |
| Batch size per GPU | 128 | 128 |
| Optimizer | SGD, learning rate 0.05, momentum 0.9, the same for every GPU count | The same |
| Epochs | 10 on CIFAR-10, 5 on synthetic images (3 in the workers sweeps) | 10 (planned) |
| Seeds | 0, 1, 2 | 0, 1, 2 for every GPU count |
| DataLoader workers per process | 8 on CIFAR-10, 4 on synthetic images | The best value of the DDP sweep in section 3 |

The tabular use case is not benchmarked yet: its training script belongs to the training runtime
(Abdullah), which is not written yet.

## 2. 1 GPU vs multi-GPU DDP (mandatory)

**Pending: the run on 2 GPUs.**

| Run | GPUs | Time per epoch | Total time | Throughput (images/s) | Speedup | Efficiency | GPU-hours | Cost (USD) | Final accuracy |
|---|---|---|---|---|---|---|---|---|---|
| single | 1 | pending | | | 1.0 | 100% | | | |
| ddp | 2 | pending | | | | | | | |

- **Speedup** = time on 1 GPU / time on N GPUs.
- **Efficiency** = speedup / N.
- **GPU-hours** = GPUs × hours; **cost** from `contracts/pricing.yaml`.

How each number is measured:

- **Time per epoch:** the mean over the epochs after the first, then the mean over the seeds. The first
  epoch is left out because it includes one-off work, such as starting the DataLoader workers: in the
  local runs it took 1.5 to 2 times as long as a later epoch. The clock is read only after the GPU has
  finished its work. Speedup and efficiency use this time.
- **Throughput:** images really processed in an epoch / time per epoch.
- **Total time:** the whole run, from starting the processes to the end of the evaluation. GPU-hours
  and cost use this time, because start-up is paid for too.
- **Cost:** total hours × the hourly price of the machine the run used. The contract prices a job by the
  whole machine, so a 2-GPU job on a 4-GPU machine pays for all four GPUs. The prices in
  `contracts/pricing.yaml` are placeholders today, so no cost is given yet.
- **Final accuracy:** after the last epoch, on the 10,000 held-out images.
- **Same workload in every row:** model, dataset, epochs, batch size per GPU and workers per process.
  The tool refuses to build the table when they differ, and it refuses runs made on a CPU. Because the
  batch size is per GPU, N GPUs take N times fewer steps per epoch, each on N times more images, with the
  same learning rate. Accuracy after the same number of epochs can therefore differ between the rows,
  which is why the table shows it.

### Local runs on 1 GPU (not the mandatory benchmark)

| Run | Dataset | GPUs | Time per epoch | Total time | Throughput (images/s) | Speedup | Efficiency | GPU-hours | Cost (USD) | Final accuracy |
|---|---|---|---|---|---|---|---|---|---|---|
| single | CIFAR-10, 10 epochs | 1 | 2.0 s | 24.9 s | 24,640 | 1.00 | 100% | 0.0069 | n/a | 74.0% |
| single | Synthetic, 5 epochs | 1 | 2.0 s | 16.8 s | 25,474 | 1.00 | 100% | 0.0047 | n/a | 76.2% |

Each row is the mean of 3 seeds. The spread between the seeds (standard deviation):

- **CIFAR-10:** 2.027 ± 0.055 s per epoch (2.7%) and 74.0 ± 1.2 points of accuracy.
- **Synthetic images:** 1.960 ± 0.044 s per epoch (2.2%) and 76.2 ± 1.9 points of accuracy.

A difference of a few percent between two settings is therefore noise until more runs confirm it. The two
rows are not a speed comparison: they differ in dataset, epochs and workers. They do show that with enough
DataLoader workers, real images train about as fast as synthetic ones (3% apart, the size of the noise).
Cost is n/a because the workstation is not a machine type in the pricing contract. Files:
[`local-cifar10-1gpu-baseline.json`](benchmarks/local-cifar10-1gpu-baseline.json) and
[`local-1gpu-baseline.json`](benchmarks/local-1gpu-baseline.json).

### Command for the cloud run

```bash
cd training
python -m distributed.benchmark scaling --gpus 1 2 --repeats 3 --machine-type <machine type> \
    --dataset cifar10 --data-dir <folder with CIFAR-10> --epochs 10 --batch-size 128 \
    --num-workers <best value from section 3> --sync-probe-steps 50 --out scaling.json
```

On a machine with 4 GPUs, use `--gpus 1 2 4`. The command prints the table above and the table of section 4.
The tool does not download CIFAR-10: `--data-dir` must already hold it (see
`training/distributed/README.md`). The same command with `--gpus 1` produced the CIFAR-10 row above.

This job lasts about 20 seconds on the workstation's GPU. The cloud GPU is slower, so it will last longer
there. If a run still takes under a few minutes, its total time and cost will mostly show start-up, and a
longer run (more epochs) should be added for the cost comparison. Time per epoch, speedup and efficiency
do not depend on the length of the run.

## 3. Data-loading parallelism

DataLoader `num_workers` vs throughput. **Local runs:** 1× RTX 5090 with 16 CPU threads, ResNet-18,
batch size 128, 3 epochs, one run per value. "Time waiting for data" is the share of the epoch in which
the training loop had no batch to work on.

### Real CIFAR-10 images

| DataLoader workers per process | Throughput (images/s) | Time per epoch | Time waiting for data |
|---|---|---|---|
| 0 | 7,154 | 7.0 s | 72% |
| 1 | 8,198 | 6.1 s | 71% |
| 2 | 16,612 | 3.0 s | 44% |
| 4 | 23,938 | 2.1 s | 5% |
| 8 | 22,737 | 2.2 s | 5% |
| 16 | 23,713 | 2.1 s | 6% |

- With no workers the GPU is starved: 72% of the epoch is spent waiting for images, and throughput is 3.3
  times below the best value.
- Real images need 4 workers before the GPU becomes the limit. Every image is cropped, flipped and
  normalised on the CPU, and one or two workers cannot do that fast enough.
- This table cannot rank 4, 8 and 16 workers. The sweep was measured twice (the second file is named below),
  and one run of a setting differed from the other by up to 11%. We use 8.

File: [`local-cifar10-workers-sweep.json`](benchmarks/local-cifar10-workers-sweep.json).

### Synthetic images

| DataLoader workers per process | Throughput (images/s) | Time per epoch | Time waiting for data |
|---|---|---|---|
| 0 | 19,982 | 2.5 s | 35% |
| 1 | 26,352 | 1.9 s | 9% |
| 2 | 26,315 | 1.9 s | 4% |
| 4 | 26,807 | 1.9 s | 4% |
| 8 | 26,177 | 1.9 s | 5% |
| 16 | 24,926 | 2.0 s | 5% |

- A synthetic image is cheap to make, so one worker is already enough here: real images needed four.
  A test with synthetic data does not tell you the right number of workers.
- 16 workers were 7% slower than 4. That is one run, so it is a hint, not a result.

File: [`local-workers-sweep.json`](benchmarks/local-workers-sweep.json).

### Starting the workers: a defect found by the real data, and fixed

The first runs on real images showed a cost that the synthetic runs had hidden: the more workers, the
longer the first epoch and the evaluation took.

| DataLoader workers per process | 0 | 1 | 2 | 4 | 8 | 16 |
|---|---|---|---|---|---|---|
| Whole run of 3 epochs, before the fix | 25.4 s | 27.0 s | 22.6 s | 27.4 s | 42.1 s | 75.1 s |
| Whole run of 3 epochs, after the fix | 27.6 s | 23.5 s | 13.7 s | 10.7 s | 11.3 s | 11.2 s |

- **Cause.** `ddp.launch` starts every training process with `spawn`, the start method that is safe with
  CUDA. A process started that way spawns its DataLoader workers too. Each worker is then a new Python that
  imports PyTorch again and receives its own copy of the dataset, one worker after the other: about 2
  seconds per worker, and the same again at the evaluation. CIFAR-10 is held in memory as one large array,
  so every copy is expensive. A synthetic dataset is tiny, so the cost stayed hidden.
- **Fix.** `ddp.make_loader` now forks its workers (`ddp.worker_context`), which is PyTorch's usual way on
  Linux. Forked workers start at once and share the dataset with their parent.
- **Effect on the 10-epoch run with 8 workers.** The whole run fell from 56.3 s to 24.9 s. The nine epochs
  after the first took 18.0 s before and 18.2 s after: the fix changed how workers start, not how fast
  training runs.
- With 0 workers there is nothing to start, and the fix does not touch that path. The difference between
  those two runs (25.4 s and 27.6 s) is noise.

Files with the runs before the fix:
[`local-cifar10-workers-sweep-spawned-workers.json`](benchmarks/local-cifar10-workers-sweep-spawned-workers.json)
and
[`local-cifar10-1gpu-baseline-spawned-workers.json`](benchmarks/local-cifar10-1gpu-baseline-spawned-workers.json).

### Pending: the sweep under DDP

The same sweep on the cloud machine, under DDP. There every process starts its own workers, and they share
the CPU cores of the machine. The best value can differ from the one above.

```bash
python -m distributed.benchmark workers --values 0 2 4 8 --strategy ddp --world-size 2 \
    --dataset cifar10 --data-dir <folder with CIFAR-10> --epochs 3 --batch-size 128 --out workers.json
```

## 4. Communication and synchronisation overhead

How much of each step is spent waiting for gradients to be shared.

Under DDP every process computes gradients on its own batch, and all processes then average them before
the optimizer step. The tool measures that cost directly (`--sync-probe-steps 50`): after training it
times 50 steps on one fixed batch with gradient sharing, and 50 more with sharing switched off (`no_sync()`
in PyTorch).

- **Sync time** = step time with sharing − step time without sharing.
- **Sync overhead** = sync time / step time without sharing.

| GPUs | Batch size per GPU | Step time | Step time without sync | Sync time | Sync overhead |
|---|---|---|---|---|---|
| 2 | 128 | pending | | | |

**Pending: the GPU numbers** (NCCL between GPUs). They come from the command in section 2.

**Functional check on a CPU. This is not GPU scaling.** To prove that DDP and the measurement work before
any cloud money is spent, we ran two DDP processes on the CPU of the workstation: Gloo backend, a tiny
3-layer model, batch size 32 per process.

| Processes | Backend | Step time | Step time without sync | Sync time | Sync overhead |
|---|---|---|---|---|---|
| 2 on one CPU | Gloo | 5.4 ms | 1.3 ms | 4.1 ms | 322% |

This says nothing about GPUs: Gloo over TCP on one CPU is not NCCL between GPUs, and both processes shared
the same CPU cores. It shows two things only: the measurement works, and for a model whose step takes
about 1 ms, sharing gradients costs several times more than the training step itself.
File: [`local-ddp-cpu-check.json`](benchmarks/local-ddp-cpu-check.json).

The other fixed cost is start-up. It shows in section 2 as the gap between the total time and the time of
the epochs: 3.6 seconds per run in the local 1-GPU runs on CIFAR-10 and 4.9 seconds on synthetic images,
including the evaluation. The start-up of a DDP job on GPUs is not measured yet.

## 5. Parallelism selector

`training/distributed/selector.py` answers one question: which strategy should this job use, and why?
The rules, checked in this order:

| # | When | Choice |
|---|---|---|
| 1 | The model does not fit in the memory of one GPU | Model parallelism (tensor or pipeline). The job form does not accept these strategies yet, so the selector reports that the platform cannot run the job today |
| 2 | Several independent experiments, such as a hyperparameter search | Parallel trials: one `single` job per trial, with no communication cost |
| 3 | Fewer than two GPUs are available | `single` |
| 4 | Otherwise | `ddp` on the most GPUs that still pay off, and `single` when no number of GPUs does |

"Pay off" is where communication overhead, dataset size and budget come in. The selector predicts the
time on n GPUs as

    time(n) = time(1) × (1 + sync overhead × (n − 1)) / n + start-up time

and accepts DDP on n GPUs only when it keeps at least 70% efficiency and fits the GPU-hour budget of the
job. A small dataset means a short job, where the start-up time eats the gain.

| Parameter | Value today | Where the real value will come from |
|---|---|---|
| Throughput on one GPU | Given with each job | Section 2 |
| Sync overhead for each added GPU | 10%, an assumption | Section 4 |
| Start-up time of a DDP job | 30 s, an assumption | Section 2: total time − time of the epochs |
| Lowest efficiency accepted | 70%, our choice | — |

With these assumed values, a second GPU pays off once the job would take more than about 3 minutes on one GPU.

**Which choice it made for each experiment**

| Experiment | What the selector was given | Choice |
|---|---|---|
| Sections 2 and 3, local | 1 GPU available | `single`: fewer than two GPUs are available |
| Section 4, CPU check | No GPU | `single`. The DDP run on the CPU was forced by hand, as a functional check |
| The local CIFAR-10 job, if 2 GPUs were free | 24,640 images/s, 50,000 images, 10 epochs: 20 seconds on one GPU | `single`: too short for the assumed 30 seconds of start-up. A prediction, not a measurement |
| Cloud, 1 vs 2 GPUs | Pending: needs the measured throughput | Pending. The benchmark runs DDP whatever the selector says, because its purpose is to measure |

**Examples of the rules.** These are predictions of the selector with the assumed values, not
measurements. The job: 33 minutes on one GPU, with four 16 GB GPUs free.

| Job | Choice |
|---|---|
| As it is | `ddp` on 4 GPUs |
| Only 1 epoch (20 seconds) | `single`: start-up outweighs the gain |
| 8 independent trials | 8 `single` jobs |
| The model needs 40 GB | Model parallelism over 3 GPUs, which the platform cannot run today |
| A budget of 0.70 GPU-hours | `ddp` on 3 GPUs (4 GPUs would use 0.76) |
| A budget of 0.60 GPU-hours | `single` (0.56 GPU-hours) |

Tensor and pipeline parallelism were not run, and nothing here simulates them: ResNet-18 has about
11 million parameters and fits on one GPU, and the job form accepts only `single` and `ddp`.

## 6. What we learned

When DDP is worth it, and when it is not. **So far, from the local runs only:**

1. **Tune data loading first.** With no DataLoader workers, training on real CIFAR-10 ran 3.3 times slower:
   72% of every epoch was spent waiting for images. Four workers removed the wait. A GPU that waits for
   data stays slow under DDP too, and a second GPU only adds a second GPU that waits.
2. **Short jobs are mostly fixed costs.** In the 25-second run on CIFAR-10, 3.6 seconds went to starting up
   and evaluating, and the first epoch took 1.5 times as long as a later one. DDP adds its own start-up on
   top, which is why the selector keeps short jobs on one GPU. The cloud run must confirm this rule.
3. **Total time needs its own check.** Before the fix in section 3, the same run took 56 seconds, and more
   than half of it (31 seconds) was DataLoader workers starting. Time per epoch, throughput and accuracy
   looked right the whole time. Only the total time showed the problem, and cost is paid on total time.
4. **Test with real data early.** The runs on synthetic images passed every check and hid that defect,
   and they pointed to 1 DataLoader worker where real images need 4.
5. **Measure the noise before comparing.** Three runs of the same setting had a spread of 2 to 3% in time
   per epoch and of 1 to 2 points in accuracy (standard deviation). Single runs of one setting differed by
   up to 11%. A difference of that size between two settings means nothing without more runs.
6. **Small models lose with DDP.** In the CPU check, sharing gradients took three times as long as the
   rest of the step. It is a CPU result, so it is a warning, not a GPU number.

**Not known until the cloud run:** the real speedup and efficiency on 2 or more GPUs, the cost of sharing
gradients over NCCL, the start-up time of a DDP job, the best number of workers under DDP, and whether a
DDP job costs more or less than the same job on one GPU.
