"""Test F: a burst of jobs at once. How long does each wait in the queue? Owner: Adel.

Submits N small CPU jobs (the walk-through's job form) at the same moment, through the gateway, then waits
until all have ended and prints, per job: when it was created, started and finished, its wait in the queue
(started_at - created_at) and its run time. Times come from Training Jobs, so they are on one clock.

Needs `make up` and a fresh `make e2e` (its dataset file must still be in LocalStack S3: after `make down`
the files are gone, see Test B).

    export DEV_AUTH_TOKEN=$(grep '^DEV_AUTH_TOKEN=' .env | cut -d= -f2)
    python3 docs/evaluation/burst.py 3          # 3 jobs (default); stops waiting after 30 min

Standard library only. GATEWAY_URL defaults to http://localhost:5810.
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

GATEWAY = os.environ.get("GATEWAY_URL", "http://localhost:5810").rstrip("/")
TOKEN = os.environ.get("DEV_AUTH_TOKEN", "")
DONE = {"SUCCEEDED", "FAILED", "CANCELLED"}
GIVE_UP_SECONDS = 30 * 60


def call(path, body=None, headers=None):
    request = urllib.request.Request(
        GATEWAY + path,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json", **(headers or {})},
        data=json.dumps(body).encode() if body is not None else None,
    )
    with urllib.request.urlopen(request, timeout=20) as answer:
        return json.load(answer)


def parse(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00")) if text else None


def template_job():
    """The newest finished walk-through job (tabular_mlp): its project and dataset are reused."""
    jobs = []
    for project in call("/api/v1/projects")["items"]:
        query = urllib.parse.urlencode({"project_id": project["project_id"]})
        jobs += call(f"/api/v1/jobs?{query}")["items"]
    done = [j for j in jobs if j["status"] == "SUCCEEDED" and j.get("spec", {}).get("model") == "tabular_mlp"]
    if not done:
        sys.exit("No finished tabular_mlp job yet: run `make e2e` first.")
    return max(done, key=lambda j: j["created_at"])


def job_form(template):
    """The walk-through's small CPU job (tests/integration/conftest.py small_job)."""
    return {
        "project_id": template["project_id"],
        "dataset_id": template["spec"]["dataset_id"],
        "dataset_version": template["spec"]["dataset_version"],
        "model": "tabular_mlp",
        "hyperparameters": {"epochs": 1, "batch_size": 4, "learning_rate": 0.05, "seed": 7, "hidden_size": 8},
        "resources": {"gpu_count": 0, "cpu_cores": 2, "memory_gb": 4},
        "parallelism": {"strategy": "single", "world_size": 1},
        "execution": {"max_runtime_minutes": 10, "retry_limit": 2},
    }


def main():
    if not TOKEN:
        sys.exit("Set DEV_AUTH_TOKEN (see the docstring).")
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    template = template_job()
    form = job_form(template)
    dataset = f"{form['dataset_id']} v{form['dataset_version']}"
    print(f"Project {template['project_id']}, dataset {dataset}, {count} jobs")

    def submit(_):
        return call("/api/v1/jobs", form, {"Idempotency-Key": str(uuid.uuid4())})["job_id"]

    sent = time.time()
    with ThreadPoolExecutor(max_workers=count) as pool:
        job_ids = list(pool.map(submit, range(count)))
    print(f"submitted {count} jobs in {time.time() - sent:.2f} s:", ", ".join(job_ids))

    jobs = {}
    while time.time() - sent < GIVE_UP_SECONDS:
        jobs = {job_id: call(f"/api/v1/jobs/{urllib.parse.quote(job_id)}") for job_id in job_ids}
        ended = sum(job["status"] in DONE for job in jobs.values())
        print(f"  +{time.time() - sent:6.0f} s: {ended} of {count} ended", flush=True)
        if ended == count:
            break
        time.sleep(15)

    print("\njob      status     created (UTC)  started   finished  wait s  run s  attempt")
    waits = []
    for job_id in job_ids:
        job = jobs[job_id]
        created, started, finished = (parse(job.get(k)) for k in ("created_at", "started_at", "finished_at"))
        wait = (started - created).total_seconds() if started and created else None
        run = (finished - started).total_seconds() if finished and started else None
        if wait is not None:
            waits.append(wait)
        clock = lambda t: t.strftime("%H:%M:%S") if t else "-"  # noqa: E731
        print(
            f"{job_id:8} {job['status']:10} {clock(created):14} {clock(started):9} {clock(finished):9}"
            f" {'-' if wait is None else f'{wait:6.1f}'} {'-' if run is None else f'{run:6.1f}'}"
            f"  {job.get('attempt')}"
        )
    firsts = [parse(j["created_at"]) for j in jobs.values()]
    lasts = [parse(j["finished_at"]) for j in jobs.values() if j.get("finished_at")]
    if len(lasts) == count:
        total = (max(lasts) - min(firsts)).total_seconds()
        print(f"\nall {count} done {total:.1f} s after the first was created")
    if waits:
        print(f"wait in the queue: min {min(waits):.1f} s, max {max(waits):.1f} s")


if __name__ == "__main__":
    main()
