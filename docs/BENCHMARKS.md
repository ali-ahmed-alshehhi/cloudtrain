# Benchmarks: training and distributed parallelism

**Owners:** Ahmed + Abdulla (Student 5). Template: fill in with **real** measurements only.
Tensor and pipeline parallelism must never be simulated and presented as real GPU scaling.

## 1. Setup
- Model and dataset: ResNet-18 on CIFAR-10 _(and the tabular use case)_
- Hardware: instance types, GPU model, GPUs per machine
- Software: PyTorch version, NCCL, batch size per GPU, epochs, seeds

## 2. 1 GPU vs multi-GPU DDP (mandatory)

| Run | GPUs | Time per epoch | Total time | Throughput (images/s) | Speedup | Efficiency | GPU-hours | Cost (USD) | Final accuracy |
|---|---|---|---|---|---|---|---|---|---|
| single | 1 | | | | 1.0 | 100% | | | |
| ddp | 2 | | | | | | | | |

- **Speedup** = time on 1 GPU / time on N GPUs.
- **Efficiency** = speedup / N.
- **GPU-hours** = GPUs × hours; **cost** from `contracts/pricing.yaml`.

## 3. Data-loading parallelism
DataLoader `num_workers` vs throughput.

## 4. Communication and synchronisation overhead
How much of each step is spent waiting for gradients to be shared.

## 5. Parallelism selector
The rules, and which choice it made for each experiment.

## 6. What we learned
When DDP is worth it, and when it is not.
