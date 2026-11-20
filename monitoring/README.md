# Monitoring (owners: Hilal + Adel, Student 10)

Proposal and agreement: **#109**. Local only: on the AWS Emulator the dashboard and alarms are CloudWatch,
built by Hamda + Fatma in `infrastructure/modules/monitoring` (decision 0011).

| Folder | What it is |
|---|---|
| `job-events-monitor/` | The only reader of the `job-events` queue: job counts, queue wait and run time per attempt ([README](job-events-monitor/README.md)) |
| `prometheus/prometheus.yml` | Reads every service's `GET /metrics` every 15 s (names and ports: `contracts/ports.md`) |
| `prometheus/alerts.yml` | 5 alert rules: service down, >5% server errors, dead letters, outbox backlog, job-events not read |
| `prometheus/alerts.test.yml` | Unit tests for the alert rules (FIXTURE series) |
| `grafana/provisioning/` | Grafana's data source (Prometheus) and dashboard folder, so nothing is clicked by hand |
| `grafana/dashboards/cloudtrain-overview.json` | The dashboard. **Generated:** edit `grafana/build_dashboard.py`, then run it |
| `aws/` | For Hamda + Fatma: CloudWatch dashboard template, alarms, and the monitor's IAM policy ([README](aws/README.md)) |

## The dashboard: "CloudTrain overview"
| Row | Panels |
|---|---|
| Is everything up? | UP/DOWN per service · number of firing alerts |
| Requests | requests/s · share of 5xx · p95 answer time, per service |
| Training jobs | submitted · succeeded · failed · retried · events per minute · time waiting in the queue · training time by result |
| Reliability | dead letters and watchdog failures · job-service outbox · job-events delay and time since the last read |
| GPUs | GPUs in use · busy workers · jobs placed (Maitha's #105; "No data yet" until it is merged) |

Panels with nothing to show say **"No data yet"**: no zeros or NaN are invented.

## Checks done
```bash
promtool check config monitoring/prometheus/prometheus.yml   # (alerts path adjusted when run outside Docker)
promtool check rules  monitoring/prometheus/alerts.yml       # 5 rules
cd monitoring/prometheus && promtool test rules alerts.test.yml
python3 monitoring/grafana/build_dashboard.py                # regenerates the JSON
```
Every dashboard query was run against a live Prometheus 3.5.0 that scraped the real gateway, the real
job-events-monitor (fed FIXTURE events from the recorded job-service output) and the real job-service
`/metrics` output (from its own test harness): no query errors, no NaN, values as expected
(queue wait average 22.5 s, run time 121 s failed / 300 s succeeded, gateway 5xx share while its
backends were stopped, scheduler shown DOWN and its alert firing).
Grafana itself was not started (its download is blocked in the build environment): the first real look
at the dashboard is on a laptop once it is in Compose.

## In Compose (#109 agreed, contract #125 merged)
`make up` starts the three containers with everything else (`docker-compose.yml`, Ali's file: he reviews
it as code owner). Ports: `contracts/ports.md`. Settings: `.env` (`GRAFANA_ADMIN_PASSWORD`,
`JOB_EVENTS_WAIT_SECONDS`, `JOB_EVENTS_HEALTHY_WITHIN_SECONDS`).

| Container | Image | Published | Health check |
|---|---|---|---|
| `job-events-monitor` | built from `monitoring/job-events-monitor` | no (8011 inside) | `GET /health` |
| `prometheus` | `prom/prometheus:v3.5.5` (pinned) | no (9090 inside) | `GET /-/ready` |
| `grafana` | `grafana/grafana:12.4.15` (pinned) | **3001, local only** | `GET /api/health` |

Open the dashboard at http://localhost:3001 (viewers read only; admin password from `.env`, never
`admin/admin`). No end-to-end test uses Grafana.

`monitoring/job-events-monitor` is in the `make test` list (`Makefile`) and in `scripts/changed_services.sh`,
so CI lints and tests it; `pip-audit` also checks `monitoring/*/requirements.txt` (`security.yml`).
