# Database design

One PostgreSQL database, **one schema and one database user per service**. A service can reach only its
own schema, so nobody reads another service's tables by accident. Locally: the `postgres` container.
Cloud: RDS PostgreSQL.

| Schema | Service | Owner | Page |
|---|---|---|---|
| `projects` | Projects | Ali | [projects.md](projects.md) |
| `datasets` | Datasets | Faisal | [datasets.md](datasets.md) |
| `jobs` | Training Jobs | Mariam | [jobs.md](jobs.md) |
| `scheduler` | Scheduler | Maitha | [scheduler.md](scheduler.md) |
| `mlflow` | MLflow | Abdullah | [mlflow.md](mlflow.md) |
| `registry` | Model Registry | Majed | [registry.md](registry.md) |
