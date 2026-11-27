"""Test B, part 3: what survives `make down` + `make up`, now including models and MLflow runs. Owner: Adel.

Prints, through the gateway, the records that live in PostgreSQL: projects with their jobs and number of
datasets, registered models, MLflow experiments and runs (status, job_id tag, accuracy). Run it before and
after the restart and compare:

    export DEV_AUTH_TOKEN=$(grep '^DEV_AUTH_TOKEN=' .env | cut -d= -f2)
    python3 docs/evaluation/snapshot.py > /tmp/before.txt
    make down && make up
    python3 docs/evaluation/snapshot.py > /tmp/after.txt
    diff /tmp/before.txt /tmp/after.txt

It does not check model files: the 22 Nov version (c274c62) counted each run's own artifact list, which is
empty in MLflow 3 (a logged model is kept apart from the run), so that section was removed.
Standard library only; it only reads. GATEWAY_URL defaults to http://localhost:5810.
"""

import json
import os
import sys
import urllib.parse
import urllib.request

GATEWAY = os.environ.get("GATEWAY_URL", "http://localhost:5810").rstrip("/")
TOKEN = os.environ.get("DEV_AUTH_TOKEN", "")


def call(path, body=None):
    request = urllib.request.Request(
        GATEWAY + path,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        data=json.dumps(body).encode() if body is not None else None,
    )
    with urllib.request.urlopen(request, timeout=20) as answer:
        return json.load(answer)


def main():
    if not TOKEN:
        sys.exit("Set DEV_AUTH_TOKEN (see the docstring).")

    print("== RECORDS (PostgreSQL)")
    for project_id in sorted(p["project_id"] for p in call("/api/v1/projects")["items"]):
        query = urllib.parse.urlencode({"project_id": project_id})
        jobs = call(f"/api/v1/jobs?{query}")["items"]
        datasets = call(f"/api/v1/datasets?{query}")["items"]
        job_list = sorted((j["job_id"], j["status"]) for j in jobs)
        print(project_id, "| jobs:", job_list, "| datasets:", len(datasets))

    models = call("/api/v1/models").get("items", [])
    print("models:", len(models), sorted(str(m.get("model_id")) for m in models))

    experiments = call("/api/v1/experiments/experiments/search", {"max_results": 100})["experiments"]
    print("MLflow experiments:", sorted(e["name"] for e in experiments))
    runs = []
    for experiment in experiments:
        runs += call(
            "/api/v1/experiments/runs/search",
            {"experiment_ids": [experiment["experiment_id"]], "max_results": 1000},
        ).get("runs", [])
    print("MLflow runs:", len(runs))
    for run in sorted(runs, key=lambda r: r["info"]["run_id"]):
        tags = {t["key"]: t["value"] for t in run.get("data", {}).get("tags", [])}
        metrics = {m["key"]: m["value"] for m in run.get("data", {}).get("metrics", [])}
        accuracy = metrics.get("final_accuracy", metrics.get("accuracy"))
        print(
            " ",
            run["info"]["run_id"],
            run["info"]["status"],
            tags.get("job_id", "-"),
            "accuracy:",
            None if accuracy is None else round(accuracy, 4),
        )


if __name__ == "__main__":
    main()
