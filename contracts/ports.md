# Ports and addresses

Only **two** ports are published to your laptop: **5810** (gateway) and **3000** (portal).
Everything else is reachable only inside the Docker network, by its container name.
Changing a port is a contract change.

| Container name | Folder | Owner(s) | Port | Published | Reached by |
|---|---|---|---|---|---|
| `gateway` | `gateway/` | Ali | 5810 | **yes** | browser, portal |
| `portal` | `portal/` | Hilal + Adel | 3000 | **yes** | browser |
| `project-service` | `project-service/` | Ali | 8001 | no | gateway, other services (membership check) |
| `dataset-service` | `dataset-service/` | Faisal | 8002 | no | gateway, job service, workers |
| `job-service` | `job-service/` | Mariam | 8003 | no | gateway, scheduler, workers |
| `scheduler` | `scheduler/` | Maitha | 8004 | no | nobody (internal only) |
| `model-registry` | `model-registry/` | Majed | 8006 | no | gateway, inference |
| `inference-service` | `inference-service/` | Majed | 8007 | no | gateway |
| `training-worker` | `training/` | Abdullah | 8010 | no | scheduler (local development only) |
| `mlflow` | `mlflow/` | Abdullah | 5000 | no | gateway (read only), workers, model registry |
| `postgres` | — | Ali (compose) | 5432 | no | services, each with its own schema and user |
| `localstack` | — | Ali (compose) | 4566 | no | SQS: job service, scheduler · S3: dataset service, workers, MLflow, registry |

Inside the Docker network a service is called by `http://<container name>:<port>`, e.g.
`http://dataset-service:8002`. The addresses are set as environment variables (`DATASET_SERVICE_URL`, ...),
never hard-coded. See `.env.example`.
