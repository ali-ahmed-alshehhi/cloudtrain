"""1 GPU vs multi-GPU (DDP): the numbers of given MLflow runs, through the gateway. Owner: Adel.

For the run IDs Ahmed + Abdulla post on #76 (#30), prints per run and per GPU count: time per epoch,
throughput, speedup, efficiency, total time, final accuracy, GPU-hours, estimated cost, and where it ran.
The arithmetic is the portal's comparison page (`portal/lib/experiments/compare.mjs`) and the benchmark
tool (`training/distributed/metrics.py`): time per epoch = mean of the epochs after the first; throughput =
images of those epochs / their seconds; one row per GPU count = mean of its runs; speedup = 1-GPU time per
epoch / N-GPU time per epoch; efficiency = speedup / N. GPU-hours and cost are Training Jobs' numbers for
each run's job, never computed here. Anything not logged is printed as "not logged" or "unknown", never 0.

    export DEV_AUTH_TOKEN=$(grep '^DEV_AUTH_TOKEN=' .env | cut -d= -f2)
    python3 docs/evaluation/compare_runs.py RUN_ID_1GPU RUN_ID_2GPU [more run IDs]

Reads only (MLflow `runs/get` and `metrics/get-history`, Training Jobs `GET /jobs/{id}`), as a member of the
runs' project. Standard library only. GATEWAY_URL defaults to http://localhost:5810.
"""

import json
import os
import statistics
import sys
import urllib.error
import urllib.parse
import urllib.request

GATEWAY = os.environ.get("GATEWAY_URL", "http://localhost:5810").rstrip("/")
TOKEN = os.environ.get("DEV_AUTH_TOKEN", "")
SAME_WORKLOAD = ("model", "dataset_id", "dataset_version", "epochs", "batch_size", "num_workers")


def get(path, **query):
    url = GATEWAY + path + ("?" + urllib.parse.urlencode(query) if query else "")
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(request, timeout=20) as answer:
        return json.load(answer)


def history(run_id, key):
    points = get("/api/v1/experiments/metrics/get-history", run_id=run_id, metric_key=key).get("metrics", [])
    return sorted(((p["step"], p["value"]) for p in points), key=lambda p: p[0])


def number(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def one_run(run_id):
    run = get("/api/v1/experiments/runs/get", run_id=run_id)["run"]
    info, data = run["info"], run.get("data", {})
    tags = {t["key"]: t["value"] for t in data.get("tags", [])}
    params = {p["key"]: p["value"] for p in data.get("params", [])}
    metrics = {m["key"]: m["value"] for m in data.get("metrics", [])}
    seconds, images = history(run_id, "epoch_seconds"), history(run_id, "epoch_images")
    steady = seconds[1:] if len(seconds) > 1 else seconds
    total = sum(value for _, value in steady)
    time_per_epoch = total / len(steady) if steady else None
    images_by_step = dict(images)
    throughput = None
    if steady and total > 0 and all(step in images_by_step for step, _ in steady):
        throughput = sum(images_by_step[step] for step, _ in steady) / total
    job = {}
    if tags.get("job_id"):
        try:
            job = get(f"/api/v1/jobs/{urllib.parse.quote(tags['job_id'])}")
        except urllib.error.HTTPError as error:
            job = {"error": error.code}
    start, end = info.get("start_time"), info.get("end_time")
    return {
        "run_id": run_id,
        "status": info.get("status"),
        "job_id": tags.get("job_id"),
        "project_id": tags.get("project_id"),
        "label": tags.get("result_label"),
        "strategy": tags.get("strategy") or params.get("strategy"),
        "world_size": tags.get("world_size") or params.get("world_size"),
        "gpus": (job.get("spec") or {}).get("resources", {}).get("gpu_count"),
        "workload": {key: params.get(key) for key in SAME_WORKLOAD},
        "epoch_seconds": [value for _, value in seconds],
        "epoch_images": [value for _, value in images],
        "time_per_epoch": time_per_epoch,
        "throughput": throughput,
        "total_seconds": (end - start) / 1000 if start and end else None,
        "accuracy": metrics.get("final_accuracy", metrics.get("accuracy")),
        "gpu_hours": number(job.get("gpu_hours")),
        "cost": number(job.get("estimated_cost_usd")),
        "machine": job.get("machine_type"),
        "job_error": job.get("error"),
    }


def mean(values):
    """Mean of all values, or None if any is missing: a mean never hides a missing run."""
    return statistics.fmean(values) if values and all(v is not None for v in values) else None


def show(value, unit="", digits=2, missing="not logged"):
    return missing if value is None else f"{value:,.{digits}f}{unit}"


def main():
    if not TOKEN:
        sys.exit("Set DEV_AUTH_TOKEN (see the docstring).")
    run_ids = sys.argv[1:]
    if len(run_ids) < 2:
        sys.exit("Give at least two MLflow run IDs: the 1-GPU run and the multi-GPU run.")
    runs = [one_run(run_id) for run_id in run_ids]

    print("== Runs")
    for r in runs:
        print(f"{r['run_id']}  {r['status']}  job {r['job_id']}  project {r['project_id']}")
        print(f"   machine {r['machine']}")
        print(f"   strategy {r['strategy']}, world_size {r['world_size']}, GPUs (job) {r['gpus']}")
        print(f"   where it ran: {r['label'] or 'NOT LABELLED (tag result_label missing)'}")
        print(f"   epoch_seconds {r['epoch_seconds'] or 'not logged'}")
        print(f"   epoch_images  {r['epoch_images'] or 'not logged'}")
        if r["job_error"]:
            print(f"   Training Jobs answered {r['job_error']} for {r['job_id']}: GPU-hours and cost unknown")

    print("\n== Same workload?")
    for key in SAME_WORKLOAD:
        values = {r["workload"][key] for r in runs}
        print(f"   {key}: {'same' if len(values) == 1 else 'DIFFERENT'} {sorted(map(str, values))}")
    labels = {r["label"] for r in runs if r["label"]}
    if len(labels) > 1:
        print(f"   NOTE: the runs ran in different places: {sorted(labels)}")

    print("\n== Per GPU count (mean of its runs)")
    by_gpus = {}
    for r in runs:
        by_gpus.setdefault(r["gpus"], []).append(r)
    baseline = mean([r["time_per_epoch"] for r in by_gpus.get(1, [])])
    header = "| GPUs | Runs | Where it ran | Time per epoch | Throughput (images/s) | Speedup | Efficiency"
    print(header + " | Total time | Final accuracy | GPU-hours | Estimated cost |")
    print("|" + "---|" * 11)
    for gpus in sorted(by_gpus, key=lambda g: (g is None, g)):
        group = by_gpus[gpus]
        tpe = mean([r["time_per_epoch"] for r in group])
        speedup = baseline / tpe if baseline is not None and tpe else None
        efficiency = speedup / gpus if speedup is not None and gpus else None
        where = " / ".join(sorted({r["label"] for r in group if r["label"]})) or "not labelled"
        cost = mean([r["cost"] for r in group])
        print(
            f"| {gpus} | {len(group)} | {where} | {show(tpe, ' s')}"
            f" | {show(mean([r['throughput'] for r in group]), '', 0)}"
            f" | {show(speedup, '×')} | {show(None if efficiency is None else efficiency * 100, '%', 0)}"
            f" | {show(mean([r['total_seconds'] for r in group]), ' s', 1)}"
            f" | {show(mean([r['accuracy'] for r in group]), '', 4)}"
            f" | {show(mean([r['gpu_hours'] for r in group]), '', 4, 'unknown')}"
            f" | {'unknown' if cost is None else f'${cost:,.4f}'} |"
        )
    if baseline is None:
        print("\nNo 1-GPU run with epoch_seconds: speedup and efficiency cannot be computed.")


if __name__ == "__main__":
    main()
