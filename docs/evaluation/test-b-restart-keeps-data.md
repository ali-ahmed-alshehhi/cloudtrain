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
MLflow runs (checked in Part 3, below), and files in S3 (lost locally, Part 1).

**Update 22 Nov:** the side finding above was reported as #126 and fixed in #142 (Faisal): a missing file now
answers `404 DATASET_FILE_MISSING` ("The file of … is missing from storage"); 503 stays for real connection errors.

## Part 3: models and MLflow runs (Sun 22 Nov 2026, 12:43–12:47, UTC+4)

**Versions:** branch `adel/compare-cost-pages` at `db26b20` (`main` at `0cf0f1c` + #156), real training worker
(#93). Just after Test E, so 27 jobs and 21 MLflow runs exist (jobs `job-07` to `job-27` are real training).

```bash
export DEV_AUTH_TOKEN=$(grep '^DEV_AUTH_TOKEN=' .env | cut -d= -f2)
python3 docs/evaluation/snapshot.py > /tmp/before.txt     # version c274c62 of the script
make down
make up
python3 docs/evaluation/snapshot.py > /tmp/after.txt
cat /tmp/before.txt
diff /tmp/before.txt /tmp/after.txt
```

Before:

```
== RECORDS (PostgreSQL)
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
project-21 | jobs: [] | datasets: 1
project-22 | jobs: [] | datasets: 1
project-23 | jobs: [('job-07', 'SUCCEEDED')] | datasets: 1
project-24 | jobs: [] | datasets: 1
project-25 | jobs: [] | datasets: 1
project-26 | jobs: [('job-08', 'SUCCEEDED')] | datasets: 1
project-27 | jobs: [] | datasets: 1
project-28 | jobs: [] | datasets: 1
project-29 | jobs: [('job-09', 'SUCCEEDED')] | datasets: 1
project-30 | jobs: [] | datasets: 1
project-31 | jobs: [] | datasets: 1
project-32 | jobs: [('job-10', 'SUCCEEDED')] | datasets: 1
project-33 | jobs: [] | datasets: 1
project-34 | jobs: [] | datasets: 1
project-35 | jobs: [('job-11', 'SUCCEEDED')] | datasets: 1
project-36 | jobs: [] | datasets: 1
project-37 | jobs: [] | datasets: 1
project-38 | jobs: [('job-12', 'SUCCEEDED')] | datasets: 1
project-39 | jobs: [] | datasets: 1
project-40 | jobs: [] | datasets: 1
project-41 | jobs: [('job-13', 'SUCCEEDED')] | datasets: 1
project-42 | jobs: [] | datasets: 1
project-43 | jobs: [] | datasets: 1
project-44 | jobs: [('job-14', 'SUCCEEDED')] | datasets: 1
project-45 | jobs: [] | datasets: 1
project-46 | jobs: [] | datasets: 1
project-47 | jobs: [('job-15', 'SUCCEEDED')] | datasets: 1
project-48 | jobs: [] | datasets: 1
project-49 | jobs: [] | datasets: 1
project-50 | jobs: [('job-16', 'SUCCEEDED')] | datasets: 1
project-51 | jobs: [] | datasets: 1
project-52 | jobs: [] | datasets: 1
project-53 | jobs: [('job-17', 'SUCCEEDED'), ('job-18', 'SUCCEEDED'), ('job-19', 'SUCCEEDED'), ('job-20', 'SUCCEEDED'), ('job-21', 'SUCCEEDED'), ('job-22', 'SUCCEEDED'), ('job-23', 'SUCCEEDED'), ('job-24', 'SUCCEEDED'), ('job-25', 'SUCCEEDED'), ('job-26', 'SUCCEEDED'), ('job-27', 'SUCCEEDED')] | datasets: 1
models: 0 []
MLflow experiments: ['Default', 'cloudtrain']
MLflow runs: 21
  02619ac5b568477887d16caf51251b35 FINISHED job-11 accuracy: 0.5
  0d1c9e60e3a344eab1cef54c4efb0d4b FINISHED job-19 accuracy: 0.5
  0f760772c47846f8a3a74ef19a3a184d FINISHED job-08 accuracy: 0.5
  2370b55a27724df5a38e4a32d9ca9ce8 FINISHED job-25 accuracy: 0.5
  3a04b990360c4c07a8279eb340be4da5 FINISHED job-26 accuracy: 0.5
  40b6498a6c7f440cab19264f8fea0a7a FINISHED job-24 accuracy: 0.5
  556f81da54d94b1aa96f8f086f8dae92 FINISHED job-15 accuracy: 0.5
  58c9a175e039489b946b45c79c319bea FINISHED job-12 accuracy: 0.5
  5cf4d894aff448749580277946e5b65c FINISHED job-14 accuracy: 0.5
  987e1420c41a4b8ba5f5d780d088b67a FINISHED job-27 accuracy: 0.5
  9db52da6e56f4b47a5bb73eb7aa4ff52 FINISHED job-13 accuracy: 0.5
  af4193586df94613b8e959e3c0fbe348 FINISHED job-22 accuracy: 0.5
  b02ddf49df1343c7abfdfaa5ddf8d93d FINISHED job-10 accuracy: 0.5
  b1522aab478743ceb8f9db9be1d33fbf FINISHED job-20 accuracy: 0.5
  c835461d0c1540a599164de1718ab1ca FINISHED job-21 accuracy: 0.5
  c9b6da8b148e4719b63c5f60c3f1cc06 FINISHED job-17 accuracy: 0.5
  d0a1bfb341d1480eb65d31c42bc338b0 FINISHED job-18 accuracy: 0.5
  d7943e5dcb9c402fa00b8ec05c03f568 FINISHED job-09 accuracy: 0.5
  dfd9eb9a6c194845a85a7e6b9c517963 FINISHED job-07 accuracy: 0.5
  eb96651f1aea401a9654c80505422fb6 FINISHED job-23 accuracy: 0.5
  f51a068b87d347d39a8ef6e31d0b3601 FINISHED job-16 accuracy: 0.5
== FILES (LocalStack S3)
  02619ac5b568477887d16caf51251b35 files: 0
  0d1c9e60e3a344eab1cef54c4efb0d4b files: 0
  0f760772c47846f8a3a74ef19a3a184d files: 0
  2370b55a27724df5a38e4a32d9ca9ce8 files: 0
  3a04b990360c4c07a8279eb340be4da5 files: 0
  40b6498a6c7f440cab19264f8fea0a7a files: 0
  556f81da54d94b1aa96f8f086f8dae92 files: 0
  58c9a175e039489b946b45c79c319bea files: 0
  5cf4d894aff448749580277946e5b65c files: 0
  987e1420c41a4b8ba5f5d780d088b67a files: 0
  9db52da6e56f4b47a5bb73eb7aa4ff52 files: 0
  af4193586df94613b8e959e3c0fbe348 files: 0
  b02ddf49df1343c7abfdfaa5ddf8d93d files: 0
  b1522aab478743ceb8f9db9be1d33fbf files: 0
  c835461d0c1540a599164de1718ab1ca files: 0
  c9b6da8b148e4719b63c5f60c3f1cc06 files: 0
  d0a1bfb341d1480eb65d31c42bc338b0 files: 0
  d7943e5dcb9c402fa00b8ec05c03f568 files: 0
  dfd9eb9a6c194845a85a7e6b9c517963 files: 0
  eb96651f1aea401a9654c80505422fb6 files: 0
```

`diff /tmp/before.txt /tmp/after.txt` printed **nothing**: the two lists are identical.

**Result.**
- **Records: all kept.** 53 projects with their 27 jobs and statuses, 58 dataset records, the 2 MLflow
  experiments and all **21 MLflow runs** with their status, `job_id` tag and accuracy are the same after
  `make down` + `make up` (PostgreSQL, `postgres-data` volume).
- **Registered models: none to check.** The model registry is empty (`models: 0`): registering a model from a
  run is Majed's step of the walk-through, still skipped in `make e2e`. Not measured.
- **Model files: not measured.** The `FILES` section counts each run's own artifact list, and it was 0 for
  every run *before* the restart too. MLflow 3 keeps a logged model as a separate "logged model", not in the
  run's artifact list, so this count could not see it. The files are in the same LocalStack S3 as the dataset
  files of Part 1, so they are expected to be lost locally (decision 0005), but this run does not show it. The
  `FILES` section was taken out of `snapshot.py` afterwards so it does not suggest otherwise.
- **The accuracy is 0.5 for every run**: the walk-through trains 1 epoch on an 8-row CSV
  (`tests/integration/conftest.py`), so this number says nothing about the model. It is listed only to check
  that the metrics survive.

