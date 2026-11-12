# contracts/ — the agreed rules between services

**Owner:** Ali (Student 1). Every change here needs Ali's approval (CODEOWNERS) **and** the affected owners.

A contract is a promise: "if you call me like this, I answer like that." Each owner may build their
service however they like, as long as it keeps these promises. That is what lets 13 people build
separately and still plug together.

| File | What it fixes | Affected owners |
|---|---|---|
| `openapi/project-service.yaml` | Projects API (8001) | Ali, everyone who checks membership |
| `openapi/dataset-service.yaml` | Datasets API (8002) | Faisal, Mariam, Abdullah, Hilal + Adel |
| `openapi/job-service.yaml` | Training Jobs API (8003), incl. the alert feed and internal status/heartbeat | Mariam, Maitha, Abdullah, Hilal + Adel |
| `openapi/scheduler.yaml` | Scheduler (8004): health and metrics only | Maitha |
| `openapi/training-worker.yaml` | Worker (8010): `/internal/run` | Abdullah, Ahmed + Abdulla, Maitha |
| `openapi/model-registry.yaml` | Model Registry API (8006), incl. `/models/{id}/production` | Majed, Hilal + Adel |
| `openapi/inference-service.yaml` | Inference API (8007) | Majed, Hilal + Adel |
| `openapi/gateway.yaml` | Gateway (5810): its own endpoints and the route table | Ali, everyone |
| `training-job.schema.json` | The training job form | Mariam, Maitha, Abdullah, Ahmed + Abdulla, Ali |
| `events/job-event.schema.json` | The job events on `job-events` and in the alert feed | Mariam, Hilal + Adel |
| `error-format.json` | The shared error format | everyone |
| `job-states.md` | Job status steps | Mariam, Maitha, Abdullah |
| `ports.md` | Ports and container names | everyone |
| `pricing.yaml` | Hourly price per machine type | Hamda + Fatma, Mariam |

Paths in each service file are as the service sees them (no `/api/v1`). The public path is
`/api/v1` + that path, through the gateway.

## How to change a contract

1. Open a **Contract change** issue (template in GitHub), tag Ali and the affected owners.
2. Agree in the issue.
3. Change the file in `contracts/` **first**, in its own pull request.
4. Then change the code.
5. Record the decision in `docs/decisions/`.

`make contract` checks every running service against its file here.
