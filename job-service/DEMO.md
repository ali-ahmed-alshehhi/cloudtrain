# Failure-recovery demo — script (Mariam, Training Jobs)

**What it shows:** a training worker dies in the middle of a job, and the platform notices on its own,
retries the job, and finishes it. No person has to do anything. **Time:** about 2 minutes.

The same scenario runs in CI on every pull request (`tests/integration/test_failure_recovery.py`),
so if the live demo misbehaves, the green CI run is the proof (see "If something goes wrong").

## Before the demo (once, 10 minutes before)

Put these short settings in `.env`, so a dead worker is noticed in 6 seconds instead of 2 minutes:

```bash
HEARTBEAT_INTERVAL_SECONDS=2
HEARTBEAT_TIMEOUT_SECONDS=6
JOB_SWEEP_INTERVAL_SECONDS=2
SQS_VISIBILITY_TIMEOUT_SECONDS=20
```

Then start everything and check it is healthy:

```bash
make reset && make up        # all containers "Healthy"
make e2e                     # optional: proves the platform works before you start
```

Open two terminals side by side: **A** for commands, **B** for watching the job.

```bash
# In both terminals: the address and the login of the gateway (laptop dev login)
export G=http://localhost:5810/api/v1
export AUTH="Authorization: Bearer $(grep ^DEV_AUTH_TOKEN .env | cut -d= -f2)"
```

## The demo

**1. Create a project and upload a tiny dataset** (terminal A)

```bash
P=$(curl -s -H "$AUTH" -H 'Content-Type: application/json' -d '{"name":"Failure demo"}' $G/projects \
    | python3 -c 'import json,sys;print(json.load(sys.stdin)["project_id"])')
printf 'radius,texture,perimeter,diagnosis\n1.0,1.1,1.2,B\n1.1,1.2,1.3,B\n0.9,1.0,1.1,B\n1.2,1.3,1.4,B\n8.0,8.1,8.2,M\n8.1,8.2,8.3,M\n7.9,8.0,8.1,M\n8.2,8.3,8.4,M\n' > /tmp/wisconsin.csv
D=$(curl -s -H "$AUTH" -F project_id=$P -F name=wisconsin -F format=csv -F file=@/tmp/wisconsin.csv $G/datasets \
    | python3 -c 'import json,sys;print(json.load(sys.stdin)["dataset_id"])')
echo "$P $D"
```

**2. Submit a training job** (terminal A). Say: *"I submit a job. The Training Jobs service checks
I'm a member of the project and that the dataset version exists, saves the job as QUEUED, and answers
straight away with 202. The job goes on the queue for the Scheduler."*

```bash
J=$(curl -s -H "$AUTH" -H 'Content-Type: application/json' $G/jobs -d "{
  \"project_id\":\"$P\",\"dataset_id\":\"$D\",\"dataset_version\":1,\"model\":\"tabular_mlp\",
  \"hyperparameters\":{\"epochs\":300,\"batch_size\":4,\"learning_rate\":0.05,\"seed\":7,\"hidden_size\":8},
  \"resources\":{\"gpu_count\":0,\"cpu_cores\":2,\"memory_gb\":4},
  \"parallelism\":{\"strategy\":\"single\",\"world_size\":1},
  \"execution\":{\"max_runtime_minutes\":30,\"retry_limit\":2}}" \
  | python3 -c 'import json,sys;print(json.load(sys.stdin)["job_id"])'); echo $J
```

(300 epochs keep it running about 30 seconds, long enough to kill the worker in the middle.)

**3. Watch the job** (terminal B). It prints every status change as it happens:

```bash
J=<the job id from terminal A>
watch -n 2 "curl -s -H '$AUTH' $G/jobs/$J/events | python3 -c 'import json,sys
for e in json.load(sys.stdin)[\"items\"]:
    d=e[\"data\"]; print(e[\"occurred_at\"][11:19], e[\"event_type\"].ljust(14), \"attempt\", d.get(\"attempt\"), d.get(\"reason\") or \"\")'"
```

Wait until you see `job.running`. Say: *"The Scheduler placed it on a worker, and the worker sends
a heartbeat every 2 seconds: 'I'm still alive'."*

**4. Kill the worker** (terminal A). Say: *"Now the machine dies in the middle of training."*

```bash
docker compose kill training-worker
```

Within about 6 seconds terminal B shows:

```
job.failed     attempt 1   no heartbeat for 6 seconds (worker-… stopped answering)
job.retrying   attempt 2   retry 1 of 2
job.scheduled  attempt 2
```

(The seconds in the reason are the real silence, so 6 to 8 is normal.)

Say: *"Nobody told the platform the worker died. My service noticed the heartbeats stopped, marked the
job FAILED with the reason, and because the job allows 2 retries, put it straight back on the queue as
attempt 2. A job can never stay RUNNING forever."*

**5. A worker comes back** (terminal A). Say: *"In the cloud a new machine would start. Here I restart
the worker."*

```bash
docker compose start training-worker
```

Terminal B shows `job.running attempt 2`, then about 30 seconds later `job.succeeded attempt 2`.

**6. The final job** (terminal A): the history, and the cost of **both** attempts.

```bash
curl -s -H "$AUTH" $G/jobs/$J | python3 -m json.tool | grep -E '"status"|"attempt"|gpu_hours|estimated_cost'
```

Say: *"It succeeded on attempt 2. The cost counts both attempts, because the failed one also used a
machine. Here it's 0, because the laptop machine (`local-cpu`) is free; on AWS it uses the real
prices."*

## If something goes wrong

| What you see | What to do |
|---|---|
| The job is `SUCCEEDED` before you killed the worker | You were too slow: submit again (step 2) and kill as soon as you see `job.running`. |
| No `job.failed` after 10 seconds | Check `.env` has `HEARTBEAT_TIMEOUT_SECONDS=6`, then `make up` again (settings are read at start). |
| `job.failed` but no `job.running attempt 2` | The worker is still down: `docker compose start training-worker`. |
| Something else, and time is short | Show the CI run of any recent pull request: step "5. End-to-end walk-through" runs this exact scenario (`test_failure_recovery.py` is not in the skipped list). |

## Questions you may be asked

- **How does it know the worker died?** The worker sends a heartbeat every `HEARTBEAT_INTERVAL_SECONDS`.
  A watchdog checks every few seconds; a RUNNING job with no heartbeat for `HEARTBEAT_TIMEOUT_SECONDS`
  is marked FAILED. The timeout must be at least 3 × the interval, so one late heartbeat is not a death.
- **Why does POST /jobs answer 202, not 201?** Training takes minutes or hours; the request only
  *accepts* the job. The user follows it through its status and the alert feed.
- **What if the queue (SQS) is down when I submit?** The job and its queue message are saved in the same
  database transaction (the "outbox"), and the message is sent when SQS is back. Nothing is lost.
- **What if the dead worker comes back and reports "done"?** Refused (409 `STALE_WORKER`): attempt 2
  belongs to another worker.
- **What if retries run out?** The job stays FAILED, and a failure report goes to `training-jobs-dlq`
  (kept 14 days) for people to look at.
- **What did you change in the shared contracts?** Three agreed changes: a repeated SCHEDULED report is
  allowed (#89, found in this very demo), a read-only status endpoint for the Scheduler (#102), and an
  unknown price is `null`, not 0 (#108).
