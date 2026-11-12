# local/ — start-up scripts for the laptop environment

**Owner:** Ali (part of the `docker-compose.yml` environment). Not used in the cloud: there, Terraform
creates the same things (Hamda + Fatma).

| File | Runs in | What it creates |
|---|---|---|
| `postgres/init.sh` | the `postgres` container, once, when its volume is empty | one user and one schema per service: `projects`, `datasets`, `jobs`, `scheduler`, `registry`, `mlflow` |
| `localstack/init.sh` | the `localstack` container, every start | S3 buckets `datasets` and `artifacts`; SQS queues `training-jobs` (with dead-letter redrive), `training-jobs-dlq`, `job-events`, all encrypted |

Why each service has its own user: a service can only touch its own schema, so nobody reads another
service's tables by accident (see `docs/database/`). Service users cannot create schemas; this script does.

LocalStack stands in for both AWS S3 and AWS SQS locally (`docs/decisions/0005-localstack-for-s3.md`).
It keeps everything in memory, so **files and queue messages are lost when it restarts**. PostgreSQL
data is kept in a Docker volume until `make reset`.
