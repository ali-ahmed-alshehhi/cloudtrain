# ruff: noqa: E501  (PromQL queries and panel descriptions are long strings that read better unbroken)
"""Builds dashboards/cloudtrain-overview.json (owners: Hilal + Adel, Student 10).

Edit the panels here, then run:  python3 monitoring/grafana/build_dashboard.py
The JSON is generated so every panel has the same layout rules, units and data source.
"""

import json
from pathlib import Path

OUT = Path(__file__).parent / "dashboards" / "cloudtrain-overview.json"
DS = {"type": "prometheus", "uid": "prometheus"}

# Shared expressions. Every service's request counter is <service>_requests_total with a `status` label
# (gateway: `route` instead of `endpoint`), so the regex covers all of them. `service` comes from prometheus.yml.
REQ = '{__name__=~".+_requests_total"}'
REQ_5XX = '{__name__=~".+_requests_total", status=~"5.."}'
DUR = '{__name__=~".+_request_duration_seconds_bucket"}'

panels: list[dict] = []
_next_id = [1]
_y = [0]


def _id() -> int:
    _next_id[0] += 1
    return _next_id[0] - 1


def row(title: str) -> None:
    panels.append(
        {
            "type": "row",
            "id": _id(),
            "title": title,
            "collapsed": False,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": _y[0]},
            "panels": [],
        }
    )
    _y[0] += 1


def targets(*exprs) -> list[dict]:
    out = []
    for i, item in enumerate(exprs):
        expr, legend = item if isinstance(item, tuple) else (item, "")
        out.append({"refId": chr(65 + i), "datasource": DS, "expr": expr, "legendFormat": legend})
    return out


def panel(kind, title, description, exprs, x, w, h, unit="short", options=None, field=None):
    defaults = {"unit": unit, "noValue": "No data yet", **(field or {})}
    item = {
        "type": kind,
        "id": _id(),
        "title": title,
        "description": description,
        "datasource": DS,
        "gridPos": {"h": h, "w": w, "x": x, "y": _y[0]},
        "targets": targets(*exprs),
        "fieldConfig": {"defaults": defaults, "overrides": []},
        "options": options or {},
    }
    panels.append(item)
    return item


def timeseries(title, description, exprs, x, w, h=8, unit="short", min0=True, max_=None):
    field = {"custom": {"lineWidth": 2, "fillOpacity": 0, "showPoints": "auto", "pointSize": 6}}
    if min0:
        field["min"] = 0
    if max_ is not None:  # a share can never pass 100%: keeps the axis at 0-100% instead of auto (10000%)
        field["max"] = max_
    opts = {
        "legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
        "tooltip": {"mode": "multi", "sort": "desc"},
    }
    return panel("timeseries", title, description, exprs, x, w, h, unit, opts, field)


def stat(title, description, exprs, x, w, h=4, unit="short", thresholds=None, mappings=None):
    field = {
        "thresholds": thresholds or {"mode": "absolute", "steps": [{"color": "text", "value": None}]},
        "mappings": mappings or [],
        "decimals": 0,
    }
    opts = {
        "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
        "colorMode": "value",
        "graphMode": "none",
        "textMode": "auto",
        "justifyMode": "auto",
    }
    return panel("stat", title, description, exprs, x, w, h, unit, opts, field)


def next_row(h):
    _y[0] += h


# ---------------- Is everything up? ----------------
row("Is everything up?")
stat(
    "Services",
    "1 = Prometheus can read the service's /metrics, 0 = down. Alert: CloudTrainServiceDown.",
    [('up{job="cloudtrain"}', "{{service}}")],
    0,
    18,
    h=5,
    thresholds={
        "mode": "absolute",
        "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}],
    },
    mappings=[
        {
            "type": "value",
            "options": {"0": {"text": "DOWN", "color": "red"}, "1": {"text": "UP", "color": "green"}},
        }
    ],
)
stat(
    "Firing alerts",
    "Alert rules in monitoring/prometheus/alerts.yml that are firing now (list: Prometheus /alerts).",
    [('count(ALERTS{alertstate="firing"}) or vector(0)', "")],
    18,
    6,
    h=5,
    thresholds={
        "mode": "absolute",
        "steps": [{"color": "green", "value": None}, {"color": "red", "value": 1}],
    },
)
next_row(5)

# ---------------- Requests ----------------
row("Requests (every service)")
timeseries(
    "Requests per second",
    "All answers, by service.",
    [(f"sum by (service) (rate({REQ}[$__rate_interval]))", "{{service}}")],
    0,
    8,
    unit="reqps",
)
timeseries(
    "Server errors (5xx)",
    "Share of answers with status 5xx, by service. Alert above 5% for 5 min.",
    [
        (
            f"sum by (service) (rate({REQ_5XX}[$__rate_interval])) / (sum by (service) (rate({REQ}[$__rate_interval])) > 0)",
            "{{service}}",
        )
    ],
    8,
    8,
    unit="percentunit",
    max_=1,
)
timeseries(
    "Slowest 5% of answers (p95)",
    "95th percentile answer time, by service.",
    [(f"histogram_quantile(0.95, sum by (service, le) (rate({DUR}[$__rate_interval]))) >= 0", "{{service}}")],
    16,
    8,
    unit="s",
)
next_row(8)

# ---------------- Training jobs ----------------
row("Training jobs (job-events, read by job-events-monitor)")
stat(
    "Submitted",
    "Jobs accepted by Training Jobs in the time range.",
    [("sum(increase(job_service_jobs_submitted_total[$__range]))", "")],
    0,
    6,
)
stat(
    "Succeeded",
    "job.succeeded events in the time range.",
    [('sum(increase(cloudtrain_job_events_total{event_type="job.succeeded"}[$__range]))', "")],
    6,
    6,
)
stat(
    "Failed",
    "job.failed events in the time range (a failed attempt may be retried).",
    [('sum(increase(cloudtrain_job_events_total{event_type="job.failed"}[$__range]))', "")],
    12,
    6,
)
stat(
    "Retried",
    "job.retrying events in the time range.",
    [("sum(increase(cloudtrain_job_retries_total[$__range]))", "")],
    18,
    6,
)
next_row(4)
timeseries(
    "Job events per minute",
    "Status changes, by event type.",
    [("sum by (event_type) (rate(cloudtrain_job_events_total[$__rate_interval])) * 60", "{{event_type}}")],
    0,
    8,
)
timeseries(
    "Waiting in the queue",
    "Per attempt, QUEUED to RUNNING. Average over the last hour, and the slowest 5% (p95).",
    [
        (
            "sum(rate(cloudtrain_job_queue_wait_seconds_sum[1h])) / (sum(rate(cloudtrain_job_queue_wait_seconds_count[1h])) > 0)",
            "average",
        ),
        (
            "histogram_quantile(0.95, sum by (le) (rate(cloudtrain_job_queue_wait_seconds_bucket[1h]))) >= 0",
            "p95",
        ),
    ],
    8,
    8,
    unit="s",
)
timeseries(
    "Training time",
    "Per attempt, RUNNING to the end, by result. Average over the last hour.",
    [
        (
            "sum by (result) (rate(cloudtrain_job_run_seconds_sum[1h])) / (sum by (result) (rate(cloudtrain_job_run_seconds_count[1h])) > 0)",
            "{{result}}",
        )
    ],
    16,
    8,
    unit="s",
)
next_row(8)

# ---------------- Reliability ----------------
row("Reliability")
timeseries(
    "Dead letters and watchdog",
    "Job messages that gave up, and jobs failed by the heartbeat watchdog.",
    [
        (
            "sum by (action) (increase(job_service_dead_letters_total[$__rate_interval]))",
            "dead letter {{action}}",
        ),
        (
            "sum by (cause) (increase(job_service_watchdog_failures_total[$__rate_interval]))",
            "watchdog {{cause}}",
        ),
    ],
    0,
    8,
)
timeseries(
    "Events waiting to be sent",
    "job-service outbox: events written but not yet on SQS. Alert above 50.",
    [("job_service_outbox_pending", "outbox")],
    8,
    8,
)
timeseries(
    "job-events reader",
    "Delay from occurred_at to being read (p95), and seconds since the last read of the queue.",
    [
        (
            "histogram_quantile(0.95, sum by (le) (rate(cloudtrain_job_event_lag_seconds_bucket[$__rate_interval]))) >= 0",
            "event delay p95",
        ),
        # > 0: before the first read the timestamp is 0 (1970), which would show as "56 years"
        ("time() - (cloudtrain_job_events_last_poll_timestamp_seconds > 0)", "since last read"),
    ],
    16,
    8,
    unit="s",
)
next_row(8)

# ---------------- GPUs ----------------
row("GPUs (scheduler, #105)")
timeseries("GPUs in use", "GPUs reserved by running jobs.", [("scheduler_gpus_in_use", "GPUs")], 0, 8)
timeseries("Busy workers", "Workers running a job.", [("scheduler_workers_busy", "workers")], 8, 8)
timeseries(
    "Jobs placed per minute",
    "Jobs the scheduler put on a worker.",
    [("sum(rate(scheduler_jobs_placed_total[$__rate_interval])) * 60", "placed")],
    16,
    8,
)
next_row(8)

dashboard = {
    "uid": "cloudtrain-overview",
    "title": "CloudTrain overview",
    "description": "Local monitoring (Prometheus). On the AWS Emulator the dashboard is CloudWatch (decision 0011). "
    "Owners: Hilal + Adel.",
    "tags": ["cloudtrain"],
    "timezone": "utc",
    "editable": False,
    "refresh": "15s",
    "time": {"from": "now-1h", "to": "now"},
    "schemaVersion": 39,
    "version": 1,
    "graphTooltip": 1,
    "annotations": {"list": []},
    "templating": {"list": []},
    "links": [],
    "panels": panels,
}

OUT.write_text(json.dumps(dashboard, indent=2) + "\n", encoding="utf-8")
print(f"wrote {OUT} ({len(panels)} panels)")
