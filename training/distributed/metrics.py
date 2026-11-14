"""Benchmark arithmetic for docs/BENCHMARKS.md: time, throughput, speedup, efficiency, GPU-hours and cost.

Plain Python (no PyTorch), so it runs anywhere. The inputs are results from `train.run`.

- speedup    = time per epoch on 1 GPU / time per epoch on N GPUs
- efficiency = speedup / N
- GPU-hours  = GPUs x hours of the whole run
- cost       = hours of the whole run x the machine's hourly price (contracts/pricing.yaml)
"""

from pathlib import Path
from statistics import mean

import yaml

PRICING = Path(__file__).resolve().parents[2] / "contracts" / "pricing.yaml"
# what must be equal for two runs to be comparable
SAME_WORKLOAD = ("model", "dataset", "train_images", "epochs", "batch_size", "num_workers")


def summarise(result: dict) -> dict:
    """The headline numbers of one run."""
    epochs = result["epochs_detail"]
    steady = epochs[1:] or epochs  # the first epoch also pays for warm-up; it is left out when there are more
    seconds = sum(epoch["seconds"] for epoch in steady)
    return {
        "time_per_epoch_s": seconds / len(steady),
        "images_per_second": sum(epoch["images"] for epoch in steady) / seconds,
        "data_wait_share": sum(epoch["data_wait_seconds"] for epoch in steady) / seconds,
        "total_seconds": result["total_seconds"],
        "accuracy": result["accuracy"],
    }


def scaling_rows(results: list[dict], hourly_usd: float | None = None) -> list[dict]:
    """One row per GPU count (the mean of its repeated runs), with speedup and efficiency against 1 GPU."""
    if any(result["gpus"] == 0 for result in results):
        raise ValueError("a CPU run is a functional check, not GPU scaling: keep it out of the scaling table")
    for key in SAME_WORKLOAD:
        if len({result[key] for result in results}) > 1:
            raise ValueError(f"the runs differ in {key}, so their times cannot be compared")
    by_gpus: dict[int, list[dict]] = {}
    for result in results:
        by_gpus.setdefault(result["gpus"], []).append(summarise(result))
    if 1 not in by_gpus:
        raise ValueError("speedup needs a 1-GPU run as the baseline")

    baseline = mean(run["time_per_epoch_s"] for run in by_gpus[1])
    rows = []
    for gpus, runs in sorted(by_gpus.items()):
        row = {key: mean(run[key] for run in runs) for key in runs[0]}
        hours = row["total_seconds"] / 3600
        speedup = baseline / row["time_per_epoch_s"]
        rows.append(
            {
                "run": "single" if gpus == 1 else "ddp",
                "gpus": gpus,
                "repeats": len(runs),
                **row,
                "speedup": speedup,
                "efficiency": speedup / gpus,
                "gpu_hours": gpus * hours,
                "cost_usd": None if hourly_usd is None else hours * hourly_usd,
            }
        )
    return rows


def hourly_price(machine_type: str) -> float:
    """The hourly price of a machine type, from contracts/pricing.yaml."""
    machines = yaml.safe_load(PRICING.read_text(encoding="utf-8"))["machine_types"]
    if machine_type not in machines:
        raise ValueError(
            f"machine type {machine_type!r} is not in {PRICING.name} (known: {', '.join(machines)})"
        )
    return machines[machine_type]["hourly_usd"]


def workers_table(results: list[dict]) -> str:
    """Markdown for docs/BENCHMARKS.md, section 3: DataLoader workers against throughput."""
    by_workers: dict[int, list[dict]] = {}
    for result in results:
        by_workers.setdefault(result["num_workers"], []).append(summarise(result))
    lines = [
        "| DataLoader workers per process | Throughput (images/s) | Time per epoch | Time waiting for data |",
        "|---|---|---|---|",
    ]
    for workers, runs in sorted(by_workers.items()):
        row = {key: mean(run[key] for run in runs) for key in runs[0]}
        lines.append(
            f"| {workers} | {row['images_per_second']:,.0f} | {row['time_per_epoch_s']:.1f} s"
            f" | {row['data_wait_share']:.0%} |"
        )
    return "\n".join(lines)


def sync_table(results: list[dict]) -> str:
    """Markdown for docs/BENCHMARKS.md, section 4: what sharing gradients adds to every DDP step."""
    lines = [
        "| GPUs | Batch size per GPU | Step time | Step time without sync | Sync time | Sync overhead |",
        "|---|---|---|---|---|---|",
    ]
    for result in results:
        probe = result["sync_probe"]
        step, without = probe["step_seconds"], probe["step_seconds_without_sync"]
        lines.append(
            f"| {result['gpus']} | {result['batch_size']} | {step * 1000:.1f} ms | {without * 1000:.1f} ms"
            f" | {(step - without) * 1000:.1f} ms | {step / without - 1:.0%} |"
        )
    return "\n".join(lines)


def scaling_table(rows: list[dict]) -> str:
    """The rows as the Markdown table of docs/BENCHMARKS.md, section 2."""
    lines = [
        "| Run | GPUs | Time per epoch | Total time | Throughput (images/s) | Speedup | Efficiency"
        " | GPU-hours | Cost (USD) | Final accuracy |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        cost = "n/a" if row["cost_usd"] is None else f"{row['cost_usd']:.4f}"
        lines.append(
            f"| {row['run']} | {row['gpus']} | {row['time_per_epoch_s']:.1f} s | {row['total_seconds']:.1f} s"
            f" | {row['images_per_second']:,.0f} | {row['speedup']:.2f} | {row['efficiency']:.0%}"
            f" | {row['gpu_hours']:.4f} | {cost} | {row['accuracy']:.1%} |"
        )
    return "\n".join(lines)
