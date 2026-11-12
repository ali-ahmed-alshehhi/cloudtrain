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

Run with `make e2e` (needs `make up` first).

## Acceptance test
`make e2e` is green from a clean clone after `make reset`.
