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
