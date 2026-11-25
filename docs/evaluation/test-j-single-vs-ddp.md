# Test J: single vs DDP through the platform, on the comparison page (raw results)

**Measured:** Wed 25 Nov 2026, about 23:20 (UTC+4), by Adel on the laptop in section 0 of `EVALUATION.md`.
**Versions:** `main` at `b087330` (the per-epoch metrics of #172, the runs of #173). `make up` rebuilt every
image (5 min 13 s on a home network); 15 of 15 healthy; `make e2e` passed.
**Where it ran:** **2 processes on CPU, local stack** (the `result_label` on every run). Not GPUs, not AWS
(decision 0011). The job asks for `gpu_count` 1 and 2, which is what the page groups by; locally both run on
`local-cpu`.

## Commands

```bash
export DEV_AUTH_TOKEN=$(grep '^DEV_AUTH_TOKEN=' .env | cut -d= -f2)
cd training
CLOUDTRAIN_TOKEN=$DEV_AUTH_TOKEN ../.venv/bin/python -m distributed.platform_compare \
  --csv distributed/data/wisconsin.csv --label "2 processes on CPU, local stack" --epochs 10 --out /tmp/compare.json
cd ..
python3 docs/evaluation/compare_runs.py <the six MLflow run IDs from /tmp/compare.json>
# then http://localhost:3000/compare, project "Single vs DDP comparison" (project-88)
```

`platform_compare` (Abdulla, #173) sends the same `tabular_mlp` job through the gateway, Training Jobs, the
Scheduler and the worker as `single` (1 process) and `ddp` (2 processes, gloo), seeds 0 to 2. `compare_runs.py`
reads the six runs back through the gateway with the comparison page's arithmetic.

## Output

```
adilaldashti@Adils-MacBook-Pro cloudtrain % export DEV_AUTH_TOKEN=$(grep '^DEV_AUTH_TOKEN=' .env | cut -d= -f2)
adilaldashti@Adils-MacBook-Pro cloudtrain % cd training
adilaldashti@Adils-MacBook-Pro training % CLOUDTRAIN_TOKEN=$DEV_AUTH_TOKEN ../.venv/bin/python -m distributed.platform_compare --csv distributed/data/wisconsin.csv --label "2 processes on CPU, local stack" --epochs 10 --out /tmp/compare.json
job-56 single seed 0: run 24abe639b4a24cf3bea619cdf9f2bd00
job-57 ddp seed 0: run 1ea3462eccc34a60b181f9a5b24a78d1
job-58 single seed 1: run e3d2ea04c5dc42cb80b5af13bcaeb3e7
job-59 ddp seed 1: run d7acdff4e24c4d3bbb920d98d5570d89
job-60 single seed 2: run 4d7400c268bb46f0a29f38ab03194411
job-61 ddp seed 2: run eddcd9144cf14f23befed7ece8c404c2
Measured: 2 processes on CPU, local stack.
| Run | Processes | Seeds | Time per epoch (ms) | Throughput (rows/s) | Speedup | Efficiency | Job wall time (s) | GPU-hours (as billed) | Accuracy |
|---|---|---|---|---|---|---|---|---|---|
| single | 1 | 3 | 26.6 | 16,822 | 1.00 | 100% | 4.9 | 0.0014 | 0.968 |
| ddp | 2 | 3 | 17.8 | 25,194 | 1.50 | 75% | 5.6 | 0.0031 | 0.968 |
adilaldashti@Adils-MacBook-Pro training % cd ..
adilaldashti@Adils-MacBook-Pro cloudtrain % git show origin/adel/evaluation:docs/evaluation/compare_runs.py > /tmp/compare_runs.py
adilaldashti@Adils-MacBook-Pro cloudtrain % python3 /tmp/compare_runs.py $(python3 -c "import json;print(' '.join(r['mlflow_run_id'] for r in json.load(open('/tmp/compare.json'))['runs']))")
== Runs
24abe639b4a24cf3bea619cdf9f2bd00  FINISHED  job job-56  project project-88
   machine local-cpu
   strategy single, world_size 1, GPUs (job) 1
   where it ran: 2 processes on CPU, local stack
   epoch_seconds [0.02835858299999927, 0.026646167000080823, 0.026081458000021485, 0.028141874999960237, 0.025137250000057065, 0.02626616700001705, 0.026060458000074505, 0.025868415999980243, 0.026079333999973642, 0.03132479099997454]
   epoch_images  [448.0, 448.0, 448.0, 448.0, 448.0, 448.0, 448.0, 448.0, 448.0, 448.0]
1ea3462eccc34a60b181f9a5b24a78d1  FINISHED  job job-57  project project-88
   machine local-cpu
   strategy ddp, world_size 2, GPUs (job) 2
   where it ran: 2 processes on CPU, local stack
   epoch_seconds [0.018725042000028225, 0.016702417000033165, 0.017042082999978447, 0.01684695799997371, 0.01692112500006715, 0.01711574999990262, 0.01695816599999489, 0.01678979200005415, 0.01668387500001245, 0.016692375000047832]
   epoch_images  [448.0, 448.0, 448.0, 448.0, 448.0, 448.0, 448.0, 448.0, 448.0, 448.0]
e3d2ea04c5dc42cb80b5af13bcaeb3e7  FINISHED  job job-58  project project-88
   machine local-cpu
   strategy single, world_size 1, GPUs (job) 1
   where it ran: 2 processes on CPU, local stack
   epoch_seconds [0.02937187499992433, 0.02607020800007831, 0.02634216599994943, 0.026586624999936248, 0.026731000000040694, 0.02670316699993691, 0.02644383300003028, 0.026948791999984678, 0.02677633399991919, 0.02659787499999311]
   epoch_images  [448.0, 448.0, 448.0, 448.0, 448.0, 448.0, 448.0, 448.0, 448.0, 448.0]
d7acdff4e24c4d3bbb920d98d5570d89  FINISHED  job job-59  project project-88
   machine local-cpu
   strategy ddp, world_size 2, GPUs (job) 2
   where it ran: 2 processes on CPU, local stack
   epoch_seconds [0.0190330839999433, 0.016795290999993995, 0.01711212500003967, 0.01730562500006272, 0.0170117919999484, 0.017272542000000612, 0.016651249999995343, 0.016963375000045744, 0.024275957999975617, 0.020032750000041233]
   epoch_images  [448.0, 448.0, 448.0, 448.0, 448.0, 448.0, 448.0, 448.0, 448.0, 448.0]
4d7400c268bb46f0a29f38ab03194411  FINISHED  job job-60  project project-88
   machine local-cpu
   strategy single, world_size 1, GPUs (job) 1
   where it ran: 2 processes on CPU, local stack
   epoch_seconds [0.025252416000057565, 0.025076040999920224, 0.02574595800001589, 0.028594999999995707, 0.024961374999975305, 0.02553404100001444, 0.025909749999982523, 0.030828874999997424, 0.02568737499996132, 0.02595237499997438]
   epoch_images  [448.0, 448.0, 448.0, 448.0, 448.0, 448.0, 448.0, 448.0, 448.0, 448.0]
eddcd9144cf14f23befed7ece8c404c2  FINISHED  job job-61  project project-88
   machine local-cpu
   strategy ddp, world_size 2, GPUs (job) 2
   where it ran: 2 processes on CPU, local stack
   epoch_seconds [0.02592120799999975, 0.02204529100004038, 0.021275166999998874, 0.018255167000006622, 0.01706858399995781, 0.017310083999973358, 0.016778000000044813, 0.017812915999911638, 0.017799082999999882, 0.017303542000036032]
   epoch_images  [448.0, 448.0, 448.0, 448.0, 448.0, 448.0, 448.0, 448.0, 448.0, 448.0]
== Same workload?
   model: same ['tabular_mlp']
   dataset_id: same ['dataset-93']
   dataset_version: same ['1']
   epochs: same ['10']
   batch_size: same ['16']
   num_workers: same ['0']
== Per GPU count (mean of its runs)
| GPUs | Runs | Where it ran | Time per epoch | Throughput (images/s) | Speedup | Efficiency | Total time | Final accuracy | GPU-hours | Estimated cost |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 3 | 2 processes on CPU, local stack | 0.03 s | 16,822 | 1.00× | 100% | 4.2 s | 0.9676 | 0.0014 | $0.0000 |
| 2 | 3 | 2 processes on CPU, local stack | 0.02 s | 25,194 | 1.50× | 75% | 5.6 s | 0.9676 | 0.0031 | $0.0000 |
adilaldashti@Adils-MacBook-Pro cloudtrain % 
```

The comparison page for project-88: [`test-j-compare-page.png`](test-j-compare-page.png).

## Summary

| | Single, 1 process | DDP, 2 processes |
|---|---|---|
| Time per epoch (mean of epochs 2-10, mean of 3 seeds) | **26.6 ms** | **17.8 ms** |
| Throughput | 16,822 rows/s | 25,194 rows/s |
| Speedup / efficiency | 1.00× / 100% | **1.50× / 75%** |
| Job wall time (`platform_compare`) | 4.9 s | 5.6 s |
| Final accuracy | 0.968 | 0.968 |
| GPU-hours as billed / estimated cost | 0.0014 / $0.00 | 0.0031 / $0.00 (`local-cpu` is priced $0) |

**The three readings agree:** `platform_compare`, `compare_runs.py` and the comparison page show the same
throughput, speedup, efficiency and accuracy for the same six runs; the page labels both rows "2 processes on
CPU, local stack". Every run logged `epoch_seconds` and `epoch_images` for all 10 epochs (448 rows per epoch,
split over the processes under DDP).

**What it means.** On this laptop, 2 processes made each epoch 1.5 times faster (75% efficiency), but each DDP job
still took 0.7 s longer from start to finish: starting two processes and their process group costs more than the
9 short epochs save. On Abdulla's laptop the same runs gave 0.96× (#76, `docs/BENCHMARKS.md`), so with epochs of
15 to 30 ms the result depends on the machine. This is a small job on CPU: it shows that the platform runs and
measures DDP end to end; it is not a GPU result. Same accuracy per seed, as expected.

**Small things seen on the page.** Time per epoch is shown in whole hundredths of a second (0.03 s and 0.02 s), too
coarse for 26.6 and 17.8 ms; the speedup is computed from the exact values. The header still says "batch 16 per
GPU" (#166 changes it to "per process").
