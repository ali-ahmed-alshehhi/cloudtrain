# Integration tests — `tests/integration/`

| Owner | Approval |
|---|---|
| Ali (Student 1) | Ali (CODEOWNERS) |

## What it must do
Run the end-to-end walk-through **through the gateway** against the whole system started by
`docker compose`, exactly as the final demo does it.

- `test_walkthrough.py` — the 12 demo steps. Steps that depend on work not yet delivered are marked
  `skip` with the owner's name and hand-off date, and are switched on as owners deliver.
- `test_failure_recovery.py` — a worker is killed mid-job, the heartbeat stops, the job goes FAILED,
  is retried, and succeeds.
- `test_refusals.py` — a bad training job is refused at submit time and never saved: unknown project,
  dataset or version (404), a dataset from another project (422), and the alert feed of a project you
  are not in (403). Every refusal uses the shared error format with a request ID.
- `test_mlflow_route.py` — the gateway's read-only MLflow route against the real MLflow: searches
  and reads work, MLflow's errors come back in the shared format, writes are blocked (405), and a
  login is needed (401).

Run with `make e2e` (needs `make up` first).

Port: — · Endpoints: none of its own; it calls only the gateway (5810).

## Acceptance test
`make e2e` is green from a clean clone after `make reset`.
