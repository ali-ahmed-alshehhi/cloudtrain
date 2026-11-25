"""Single vs DDP through the whole platform (#30): gateway -> Training Jobs -> Scheduler -> worker -> MLflow.

    cd training
    CLOUDTRAIN_TOKEN=<DEV_AUTH_TOKEN from ../.env> python -m distributed.platform_compare \
        --csv distributed/data/wisconsin.csv --label "2 processes on CPU, local stack" \
        --out ../docs/benchmarks/platform-cpu-single-vs-ddp.json

It creates a project, uploads the CSV, then submits the same `tabular_mlp` job as `single` (1 process) and as
`ddp` (2 processes), once per seed, and waits for each to finish. From MLflow (through the gateway, read only)
it reads the per-epoch `epoch_seconds` and `epoch_images`; from Training Jobs the machine, GPU-hours and cost.
It saves everything to `--out` and prints the table for docs/BENCHMARKS.md.

The gateway's MLflow route is read only, so the label (the MLflow tag `result_label` that the comparison page
shows) is set inside the local stack with `docker compose exec mlflow`. That is why this tool is for the
local stack only. Locally every process runs on the CPU, so the numbers are labelled as such, never as GPUs.
"""

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from statistics import mean

import httpx

REPO = Path(__file__).resolve().parents[2]
FINAL = ("SUCCEEDED", "FAILED", "CANCELLED")


def job_form(
    project_id: str, dataset_id: str, processes: int, seed: int, epochs: int, batch_size: int
) -> dict:
    """The same workload for every run; only the strategy, the process count and the seed change."""
    return {
        "project_id": project_id,
        "dataset_id": dataset_id,
        "dataset_version": 1,
        "model": "tabular_mlp",
        "hyperparameters": {
            "epochs": epochs,
            "batch_size": batch_size,  # per process
            "learning_rate": 0.05,
            "seed": seed,
            "num_workers": 0,
        },
        # the contract: for ddp, world_size = gpu_count. Locally the Scheduler runs every job on local-cpu.
        "resources": {"gpu_count": processes, "cpu_cores": 2, "memory_gb": 2},
        "parallelism": {"strategy": "single" if processes == 1 else "ddp", "world_size": processes},
        "execution": {"max_runtime_minutes": 30, "retry_limit": 0},
    }


def wait_until_final(gateway: httpx.Client, job_id: str, timeout_seconds: float = 900) -> dict:
    """Ask Training Jobs for the job's status: at least 5 s apart, then backing off (the shared rule)."""
    waited, wait = 0.0, 5.0
    while waited < timeout_seconds:
        time.sleep(wait)
        waited += wait
        job = gateway.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in FINAL:
            return job
        wait = min(wait * 1.5, 15.0)
    raise TimeoutError(f"{job_id} did not finish within {timeout_seconds} s")


def mlflow_run(gateway: httpx.Client, job: dict) -> dict:
    experiment = gateway.get(
        "/api/v1/experiments/experiments/get-by-name", params={"experiment_name": "cloudtrain"}
    ).json()["experiment"]
    found = gateway.post(
        "/api/v1/experiments/runs/search",
        json={
            "experiment_ids": [experiment["experiment_id"]],
            "filter": f"tags.job_id = '{job['job_id']}' and tags.project_id = '{job['project_id']}'",
            "max_results": 1,
        },
    )
    found.raise_for_status()
    return found.json()["runs"][0]


def history(gateway: httpx.Client, run_id: str, key: str) -> list[float]:
    """One value per epoch, in epoch order."""
    answer = gateway.get(
        "/api/v1/experiments/metrics/get-history", params={"run_id": run_id, "metric_key": key}
    )
    answer.raise_for_status()
    points = sorted(answer.json().get("metrics", []), key=lambda point: point["step"])
    return [point["value"] for point in points]


def set_label(run_id: str, label: str) -> None:
    code = (
        "import sys, mlflow; "
        "mlflow.MlflowClient('http://localhost:5000').set_tag(sys.argv[1], 'result_label', sys.argv[2])"
    )
    subprocess.run(
        ["docker", "compose", "exec", "-T", "mlflow", "python", "-c", code, run_id, label],
        cwd=REPO,
        check=True,
    )


def summarise(run: dict) -> dict:
    """Like metrics.summarise: the first epoch is left out as warm-up."""
    seconds, images = run["epoch_seconds"][1:], run["epoch_images"][1:]
    return {"time_per_epoch_s": mean(seconds), "images_per_second": sum(images) / sum(seconds)}


def table(runs: list[dict], label: str) -> str:
    """Markdown for docs/BENCHMARKS.md: one row per process count, the mean over the seeds."""
    by_processes: dict[int, list[dict]] = {}
    for run in runs:
        by_processes.setdefault(run["processes"], []).append(run)
    baseline = mean(summarise(run)["time_per_epoch_s"] for run in by_processes[1])
    lines = [
        f"Measured: {label}.",
        "",
        "| Run | Processes | Seeds | Time per epoch (ms) | Throughput (rows/s) | Speedup | Efficiency "
        "| Job wall time (s) | GPU-hours (as billed) | Accuracy |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for processes, group in sorted(by_processes.items()):
        rows = [summarise(run) for run in group]
        per_epoch = mean(row["time_per_epoch_s"] for row in rows)
        speedup = baseline / per_epoch
        cells = [
            "single" if processes == 1 else "ddp",
            str(processes),
            str(len(group)),
            f"{per_epoch * 1000:.1f}",
            f"{mean(row['images_per_second'] for row in rows):,.0f}",
            f"{speedup:.2f}",
            f"{speedup / processes:.0%}",
            f"{mean(run['wall_seconds'] for run in group):.1f}",
            f"{mean(run['gpu_hours'] for run in group):.4f}",
            f"{mean(run['accuracy'] for run in group):.3f}",
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--csv", type=Path, required=True, help="the Wisconsin CSV to upload")
    parser.add_argument("--label", required=True, help='where it ran, e.g. "2 processes on CPU, local stack"')
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()
    if args.epochs < 3:
        parser.error("use at least 3 epochs: the first is left out as warm-up")

    url = os.environ.get("GATEWAY_URL", "http://localhost:5810")
    headers = {"Authorization": f"Bearer {os.environ['CLOUDTRAIN_TOKEN']}"}
    with httpx.Client(base_url=url, headers=headers, timeout=60) as gateway:
        project = gateway.post("/api/v1/projects", json={"name": "Single vs DDP comparison"}).json()
        dataset = gateway.post(
            "/api/v1/datasets",
            data={"project_id": project["project_id"], "name": "wisconsin-breast-cancer", "format": "csv"},
            files={"file": (args.csv.name, args.csv.read_bytes(), "text/csv")},
        )
        dataset.raise_for_status()
        dataset_id = dataset.json()["dataset_id"]

        runs = []
        for seed in args.seeds:
            for processes in (1, 2):
                form = job_form(
                    project["project_id"], dataset_id, processes, seed, args.epochs, args.batch_size
                )
                submitted = gateway.post("/api/v1/jobs", json=form)
                submitted.raise_for_status()
                job = wait_until_final(gateway, submitted.json()["job_id"])
                if job["status"] != "SUCCEEDED":
                    raise RuntimeError(f"{job['job_id']} ended {job['status']}")
                run_id = mlflow_run(gateway, job)["info"]["run_id"]
                set_label(run_id, args.label)
                runs.append(
                    {
                        "job_id": job["job_id"],
                        "mlflow_run_id": run_id,
                        "processes": processes,
                        "strategy": form["parallelism"]["strategy"],
                        "seed": seed,
                        "machine_type": job["machine_type"],
                        "gpu_hours": job["gpu_hours"],
                        "estimated_cost_usd": job["estimated_cost_usd"],
                        "started_at": job["started_at"],
                        "finished_at": job["finished_at"],
                        "wall_seconds": _seconds_between(job["started_at"], job["finished_at"]),
                        "epoch_seconds": history(gateway, run_id, "epoch_seconds"),
                        "epoch_images": history(gateway, run_id, "epoch_images"),
                        "accuracy": history(gateway, run_id, "accuracy")[-1],
                    }
                )
                print(
                    f"{job['job_id']} {form['parallelism']['strategy']} seed {seed}: run {run_id}", flush=True
                )

    saved = {
        "experiment": "platform-single-vs-ddp",
        "label": args.label,
        "project_id": project["project_id"],
        "dataset_id": dataset_id,
        "workload": {key: value for key, value in form["hyperparameters"].items() if key != "seed"},
        "model": "tabular_mlp",
        "runs": runs,
    }
    args.out.write_text(json.dumps(saved, indent=2) + "\n")
    print(table(runs, args.label))


def _seconds_between(start: str, end: str) -> float:
    from datetime import datetime

    return (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()


if __name__ == "__main__":
    main()
