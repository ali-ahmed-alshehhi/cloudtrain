"""Test H: a worker killed in the middle of a job. How long until the job is marked FAILED, retried and
finished? Owner: Adel. The same scenario as tests/integration/test_failure_recovery.py (Mariam, #145),
with the times written down.

Needs the short heartbeat settings of that test in .env (then `make down && make up && make e2e`):
    HEARTBEAT_INTERVAL_SECONDS=2
    HEARTBEAT_TIMEOUT_SECONDS=6
    JOB_SWEEP_INTERVAL_SECONDS=2
    SQS_VISIBILITY_TIMEOUT_SECONDS=20
With the default settings (120 s timeout) the same steps take minutes; the times scale with these values.
Remove the four lines afterwards and run `make down && make up` again.

    export DEV_AUTH_TOKEN=$(grep '^DEV_AUTH_TOKEN=' .env | cut -d= -f2)
    python3 docs/evaluation/recovery.py 3        # 3 runs, from the repository root (it uses docker compose)

Each run: submit a 300-epoch job (about 30 s of training), wait until RUNNING, wait 3 s, kill the worker
(`docker compose kill training-worker`), wait for job.retrying, start the worker again, wait for SUCCEEDED.
Times are from the moment of the kill (laptop clock) to each event's occurred_at (Docker's clock; Test E
found the two within 0.03 s). Standard library only. GATEWAY_URL defaults to http://localhost:5810.
"""

import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime

GATEWAY = os.environ.get("GATEWAY_URL", "http://localhost:5810").rstrip("/")
TOKEN = os.environ.get("DEV_AUTH_TOKEN", "")


def call(path, body=None):
    request = urllib.request.Request(
        GATEWAY + path,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "Idempotency-Key": str(uuid.uuid4()),
        },
        data=json.dumps(body).encode() if body is not None else None,
    )
    with urllib.request.urlopen(request, timeout=20) as answer:
        return json.load(answer)


def compose(*args):
    subprocess.run(["docker", "compose", *args], check=True, capture_output=True)


def env_setting(name, default):
    try:
        for line in open(".env"):
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip()
    except FileNotFoundError:
        pass
    return default


def wait_for(check, what, timeout=300, every=0.2):
    end = time.time() + timeout
    while time.time() < end:
        value = check()
        if value:
            return value
        time.sleep(every)
    sys.exit(f"Gave up waiting for {what} after {timeout} s.")


def template_job():
    jobs = []
    for project in call("/api/v1/projects")["items"]:
        query = urllib.parse.urlencode({"project_id": project["project_id"]})
        jobs += call(f"/api/v1/jobs?{query}")["items"]
    done = [j for j in jobs if j["status"] == "SUCCEEDED" and j.get("spec", {}).get("model") == "tabular_mlp"]
    if not done:
        sys.exit("No finished tabular_mlp job yet: run `make e2e` first.")
    return max(done, key=lambda j: j["created_at"])


def one_run(template):
    form = {
        "project_id": template["project_id"],
        "dataset_id": template["spec"]["dataset_id"],
        "dataset_version": template["spec"]["dataset_version"],
        "model": "tabular_mlp",
        "hyperparameters": {
            "epochs": 300,
            "batch_size": 4,
            "learning_rate": 0.05,
            "seed": 7,
            "hidden_size": 8,
        },
        "resources": {"gpu_count": 0, "cpu_cores": 2, "memory_gb": 4},
        "parallelism": {"strategy": "single", "world_size": 1},
        "execution": {"max_runtime_minutes": 10, "retry_limit": 2},
    }
    job_id = call("/api/v1/jobs", form)["job_id"]
    path = f"/api/v1/jobs/{urllib.parse.quote(job_id)}"
    wait_for(lambda: call(path)["status"] == "RUNNING", f"{job_id} to run")
    time.sleep(3)
    killed = time.time()
    compose("kill", "training-worker")
    try:
        wait_for(
            lambda: any(e["event_type"] == "job.retrying" for e in call(path + "/events")["items"]), "retry"
        )
    finally:
        restarted = time.time()
        compose("start", "training-worker")
    final = wait_for(
        lambda: call(path)["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"} and call(path), "end"
    )
    events = call(path + "/events")["items"]
    print(
        f"\n{job_id}: {final['status']}, attempt {final.get('attempt')}; worker started again "
        f"{restarted - killed:.1f} s after the kill"
    )
    since = {}
    for event in events:
        at = datetime.fromisoformat(event["occurred_at"].replace("Z", "+00:00")).timestamp()
        attempt = (event.get("data") or {}).get("attempt")
        reason = (event.get("data") or {}).get("reason") or ""
        print(f"  {event['event_type']:14} attempt {attempt}  {at - killed:+7.1f} s  {reason[:60]}")
        if at > killed:  # the first event of each kind after the kill
            since.setdefault(event["event_type"], at - killed)
    return since


def main():
    if not TOKEN:
        sys.exit("Set DEV_AUTH_TOKEN (see the docstring).")
    timeout = float(env_setting("HEARTBEAT_TIMEOUT_SECONDS", "120"))
    if timeout > 30:
        sys.exit(f"HEARTBEAT_TIMEOUT_SECONDS is {timeout:g}: put the short settings in .env first.")
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    names = ["HEARTBEAT_INTERVAL_SECONDS", "JOB_SWEEP_INTERVAL_SECONDS", "SQS_VISIBILITY_TIMEOUT_SECONDS"]
    others = ", ".join(f"{name}={env_setting(name, '?')}" for name in names)
    print(f"HEARTBEAT_TIMEOUT_SECONDS={timeout:g}, {others}; {runs} runs")
    template = template_job()
    results = [one_run(template) for _ in range(runs)]
    print("\nseconds after the kill   " + "  ".join(f"run {i + 1:>2}" for i in range(runs)))
    for label, key in [
        ("job.failed (detected)", "job.failed"),
        ("job.retrying", "job.retrying"),
        ("running again (try 2)", "job.running"),
        ("job.succeeded", "job.succeeded"),
    ]:
        cells = [f"{r[key]:6.1f}" if key in r else "     -" for r in results]
        print(f"{label:24} " + "  ".join(cells))


if __name__ == "__main__":
    main()
