"""List every job of every project, through the gateway (Test D, section 3).

One line per job: id, status, machine type, GPU-hours, estimated cost, and finished_at - started_at in
seconds. Standard library only. Reads the gateway address and the local dev token from the environment:

    export DEV_AUTH_TOKEN=$(grep '^DEV_AUTH_TOKEN=' .env | cut -d= -f2)
    python3 docs/evaluation/jobs.py                    # GATEWAY_URL defaults to http://localhost:5810

The run on 22 Nov used a throwaway script in /tmp that was not kept. This file is a re-creation that prints
the same columns, added afterwards so the test can be repeated; it was checked against a fake gateway, not
against the 22 Nov stack. It only reads: GET /api/v1/projects and GET /api/v1/jobs?project_id=...
"""

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime

GATEWAY = os.environ.get("GATEWAY_URL", "http://localhost:5810").rstrip("/")
TOKEN = os.environ.get("DEV_AUTH_TOKEN", "")


def get(path):
    request = urllib.request.Request(GATEWAY + path, headers={"Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(request, timeout=10) as answer:
        return json.load(answer)


def seconds_between(start, end):
    if not start or not end:
        return None
    parse = lambda text: datetime.fromisoformat(text.replace("Z", "+00:00"))  # noqa: E731
    return round((parse(end) - parse(start)).total_seconds(), 1)


def main():
    if not TOKEN:
        sys.exit("Set DEV_AUTH_TOKEN (see the docstring).")
    jobs = []
    for project in get("/api/v1/projects")["items"]:
        query = urllib.parse.urlencode({"project_id": project["project_id"]})
        jobs.extend(get(f"/api/v1/jobs?{query}")["items"])
    for job in sorted(jobs, key=lambda j: j["job_id"]):
        run_s = seconds_between(job.get("started_at"), job.get("finished_at"))
        print(job["job_id"], job["status"], job.get("machine_type"),
              "gpu_hours:", job.get("gpu_hours"), "cost:", job.get("estimated_cost_usd"), "run_s:", run_s)


if __name__ == "__main__":
    main()
