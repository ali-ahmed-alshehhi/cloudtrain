# Test B: does data survive `make down` + `make up`? (raw results)

**Measured:** Thu 19 Nov 2026, 09:19–09:27 (UTC+4), by Adel on a MacBook Pro, right after Test A.
**Versions:** Git `f8d8dab` (`main`), Docker Compose v5.6.1. `make down` = `docker compose down`
(containers removed, the `postgres-data` volume kept). All 12 containers healthy again after `make up`.

## Commands (all through the gateway, port 5810)

```bash
DEV_AUTH_TOKEN=$(grep '^DEV_AUTH_TOKEN=' .env | cut -d= -f2)  # the local-only login from .env
P=$(curl -s -X POST -H "Authorization: Bearer $DEV_AUTH_TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"Test B restart","description":"Evaluation: data survives make down / make up"}' \
  http://localhost:5810/api/v1/projects | sed -E 's/.*"project_id":"([^"]+)".*/\1/')
printf 'x,y\n1,2\n3,4\n' > /tmp/testb.csv; shasum -a 256 /tmp/testb.csv
D=$(curl -s -X POST -H "Authorization: Bearer $DEV_AUTH_TOKEN" -F project_id=$P -F name="Test B file" \
  -F format=csv -F file=@/tmp/testb.csv http://localhost:5810/api/v1/datasets | sed -E 's/.*"dataset_id":"([^"]+)".*/\1/')
check() {  # project record, dataset record, dataset file
  curl -s -o /dev/null -w "project: %{http_code}\n" -H "Authorization: Bearer $DEV_AUTH_TOKEN" http://localhost:5810/api/v1/projects/$P
  curl -s -o /dev/null -w "dataset record: %{http_code}\n" -H "Authorization: Bearer $DEV_AUTH_TOKEN" http://localhost:5810/api/v1/datasets/$D
  curl -s -w "\nfile download: %{http_code}\n" -H "Authorization: Bearer $DEV_AUTH_TOKEN" http://localhost:5810/api/v1/datasets/$D/versions/1/download
}
check; make down; make up; check
```

Created: `project-01`, `dataset-01` (CSV, SHA-256 `2a2b86e7…80f7a3`).

## Before the restart

```
project: 200
dataset record: 200
x,y
1,2
3,4

file download: 200
```

## After `make down` + `make up`

```
project: 200
dataset record: 200
{"error":{"code":"SERVICE_UNAVAILABLE","message":"Object storage is not reachable","request_id":"req-37aa850b"}}
file download: 503
```

## What it means

| Kept where | Survived? |
|---|---|
| Records in PostgreSQL (project, dataset metadata) | ✅ Yes |
| Files in LocalStack S3 (the dataset file) | ❌ No: lost |

This is the trade-off written in [decision 0005](../decisions/0005-localstack-for-s3.md): free LocalStack keeps
S3 in memory, so files are lost when it restarts; real AWS S3 in the cloud is not affected (not measurable
here, decision 0011). Model files and MLflow run files use the same LocalStack S3 (`artifacts` bucket), so
the same is expected for them; not measured (no models yet).

Side finding: after the restart, S3 itself was reachable (LocalStack healthy, buckets re-created by
`local/localstack/init.sh`); only the file was missing. `dataset-service` reports every S3 error as
`503 Object storage is not reachable` (`dataset-service/app/storage.py`), so the message points to the wrong cause.

## Part 2: every record, including jobs (Sat 21 Nov 2026, 18:15, UTC+4)

**Versions:** branch `adel/job-events-monitor` at `b404125` (`main` at `474a732` + #115), Docker Compose v5.6.1.
A small script lists, through the gateway, every project with its jobs (id and status) and number of datasets,
and the MLflow experiments; it runs before `make down` and after `make up`, and the two lists are compared.

```bash
cat > /tmp/snapshot.py <<'PY'
import json, os, urllib.request
AUTH = {"Authorization": os.environ["H"].split(": ", 1)[1], "Content-Type": "application/json"}
def get(path, body=None):
    req = urllib.request.Request("http://localhost:5810" + path, headers=AUTH, data=body)
    return json.load(urllib.request.urlopen(req))
for p in sorted(x["project_id"] for x in get("/api/v1/projects")["items"]):
    jobs = get(f"/api/v1/jobs?project_id={p}")["items"]
    datasets = get(f"/api/v1/datasets?project_id={p}")["items"]
    print(p, "| jobs:", sorted((j["job_id"], j["status"]) for j in jobs), "| datasets:", len(datasets))
exps = get("/api/v1/experiments/experiments/search", json.dumps({"max_results": 100}).encode())["experiments"]
print("MLflow experiments:", sorted(e["name"] for e in exps))
PY
export H   # the login from .env, as in Part 1
.venv/bin/python /tmp/snapshot.py > /tmp/before.txt
make down; make up
.venv/bin/python /tmp/snapshot.py > /tmp/after.txt
diff /tmp/before.txt /tmp/after.txt && echo "SAME: every record survived the restart"
```

Before (and, identical, after):

```
project-01 | jobs: [] | datasets: 1
project-02 | jobs: [] | datasets: 1
project-03 | jobs: [] | datasets: 1
project-04 | jobs: [('job-01', 'SUCCEEDED')] | datasets: 1
project-05 | jobs: [] | datasets: 1
project-06 | jobs: [] | datasets: 1
project-07 | jobs: [('job-02', 'SUCCEEDED')] | datasets: 1
project-08 | jobs: [] | datasets: 1
project-09 | jobs: [] | datasets: 1
project-10 | jobs: [('job-03', 'SUCCEEDED')] | datasets: 1
project-11 | jobs: [] | datasets: 6
project-12 | jobs: [] | datasets: 1
project-13 | jobs: [] | datasets: 1
project-14 | jobs: [('job-04', 'SUCCEEDED')] | datasets: 1
project-15 | jobs: [] | datasets: 1
project-16 | jobs: [] | datasets: 1
project-17 | jobs: [('job-05', 'SUCCEEDED')] | datasets: 1
project-18 | jobs: [] | datasets: 1
project-19 | jobs: [] | datasets: 1
project-20 | jobs: [('job-06', 'SUCCEEDED')] | datasets: 1
MLflow experiments: ['Default']
```

```
SAME: every record survived the restart
```

**Result:** 20 projects, 6 jobs (all `SUCCEEDED`), 25 dataset records and the MLflow experiment list are the same
after `make down` + `make up`: all live in PostgreSQL (`postgres-data` volume). The 6 jobs were run by the
**stand-in worker** of the walk-through (`make e2e`), not by real training. Not covered yet: model records and
MLflow runs (none exist until real training, #93), and files in S3 (lost locally, Part 1).

**Update 22 Nov:** the side finding above was reported as #126 and fixed in #142 (Faisal): a missing file now
answers `404 DATASET_FILE_MISSING` ("The file of … is missing from storage"); 503 stays for real connection errors.
