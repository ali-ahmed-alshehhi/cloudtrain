# API specifications

The OpenAPI specifications live in `contracts/openapi/` (one source, so they can never drift apart):

| Service | Specification |
|---|---|
| API Gateway | [`contracts/openapi/gateway.yaml`](../../contracts/openapi/gateway.yaml) |
| Projects | [`contracts/openapi/project-service.yaml`](../../contracts/openapi/project-service.yaml) |
| Datasets | [`contracts/openapi/dataset-service.yaml`](../../contracts/openapi/dataset-service.yaml) |
| Training Jobs | [`contracts/openapi/job-service.yaml`](../../contracts/openapi/job-service.yaml) |
| Scheduler | [`contracts/openapi/scheduler.yaml`](../../contracts/openapi/scheduler.yaml) |
| Training worker | [`contracts/openapi/training-worker.yaml`](../../contracts/openapi/training-worker.yaml) |
| Model Registry | [`contracts/openapi/model-registry.yaml`](../../contracts/openapi/model-registry.yaml) |
| Inference | [`contracts/openapi/inference-service.yaml`](../../contracts/openapi/inference-service.yaml) |

Shared shapes: [`training-job.schema.json`](../../contracts/training-job.schema.json),
[`events/job-event.schema.json`](../../contracts/events/job-event.schema.json),
[`error-format.json`](../../contracts/error-format.json).

Each running service also publishes its own at `/openapi.json`; `make contract` checks that each one
behaves as its file says. Public paths are `/api/v1` + the service path, through the gateway on port 5810.
