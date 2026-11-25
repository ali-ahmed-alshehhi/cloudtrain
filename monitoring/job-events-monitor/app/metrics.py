"""Prometheus metrics of the monitor (scraped by Prometheus) and the same numbers as CloudWatch EMF lines.

All names start with cloudtrain_job_ so the dashboard can find them. `Metrics(registry)` lets tests use
their own registry; the service uses the default one, which GET /metrics serves.
"""

import json
from datetime import datetime

from prometheus_client import REGISTRY, CollectorRegistry, Counter, Gauge, Histogram

from app.tracker import INVALID_REASONS, TERMINAL, Outcome

# Small buckets too: laptop jobs wait about 0.04 s and train about 3 s (Test D, 22 Nov). With 1 s and 10 s as
# the smallest buckets, every such job fell in the first one and p50/p95 said only "under 1 s" / "under 10 s".
WAIT_BUCKETS = (0.1, 0.25, 0.5, 1, 5, 15, 30, 60, 120, 300, 600, 1800, 3600)
RUN_BUCKETS = (1, 2.5, 5, 10, 30, 60, 300, 600, 1800, 3600, 7200, 14400, 28800)
LAG_BUCKETS = (0.1, 0.5, 1, 2, 5, 10, 30, 60, 300)


class Metrics:
    def __init__(self, registry: CollectorRegistry = REGISTRY) -> None:
        self.events = Counter(
            "cloudtrain_job_events_total",
            "Job events read from job-events, by type",
            ["event_type"],
            registry=registry,
        )
        self.retries = Counter("cloudtrain_job_retries_total", "job.retrying events", registry=registry)
        self.duplicates = Counter(
            "cloudtrain_job_events_duplicate_total",
            "Events ignored because their event_id was seen",
            registry=registry,
        )
        self.invalid = Counter(
            "cloudtrain_job_events_invalid_total",
            "Messages that are not a valid job event (not_json, schema, bad_time)",
            ["reason"],
            registry=registry,
        )
        self.queue_wait = Histogram(
            "cloudtrain_job_queue_wait_seconds",
            "Time from QUEUED to RUNNING, per attempt",
            buckets=WAIT_BUCKETS,
            registry=registry,
        )
        self.run = Histogram(
            "cloudtrain_job_run_seconds",
            "Time from RUNNING to the end of the attempt, by result",
            ["result"],
            buckets=RUN_BUCKETS,
            registry=registry,
        )
        self.lag = Histogram(
            "cloudtrain_job_event_lag_seconds",
            "Time from occurred_at to reading the event",
            buckets=LAG_BUCKETS,
            registry=registry,
        )
        self.poll_errors = Counter(
            "cloudtrain_job_events_poll_errors_total",
            "Failed reads or deletes on the job-events queue",
            registry=registry,
        )
        self.last_poll = Gauge(
            "cloudtrain_job_events_last_poll_timestamp_seconds",
            "Unix time of the last successful read",
            registry=registry,
        )
        self.attempts_tracked = Gauge(
            "cloudtrain_job_attempts_tracked",
            "Job attempts whose timings are kept in memory",
            registry=registry,
        )

    def start_at_zero(self, event_types) -> None:
        """Create every labelled series at 0 before the first event.

        A labelled series only appears at its first .inc(). If Prometheus first sees it at 3, increase()
        counts from 3 and the dashboard shows 1 success instead of 3 (seen on a laptop, 20 Nov), and a
        type that never happened shows "No data" instead of 0.
        """
        for event_type in event_types:
            self.events.labels(event_type)
        for result in TERMINAL.values():
            self.run.labels(result)
        for reason in INVALID_REASONS:
            self.invalid.labels(reason)

    def record(self, outcome: Outcome) -> None:
        if outcome.kind == "duplicate":
            self.duplicates.inc()
            return
        if outcome.kind == "invalid":
            self.invalid.labels(outcome.reason).inc()
            return
        for seen in outcome.observations:
            if seen.name == "events":
                self.events.labels(seen.labels["event_type"]).inc()
            elif seen.name == "retries":
                self.retries.inc()
            elif seen.name == "lag_seconds":
                self.lag.observe(seen.value)
            elif seen.name == "queue_wait_seconds":
                self.queue_wait.observe(seen.value)
            elif seen.name == "run_seconds":
                self.run.labels(seen.labels["result"]).observe(seen.value)


# ---------- CloudWatch Embedded Metric Format ----------
# A JSON log line in this shape becomes CloudWatch metrics on AWS, with only log permissions.
# https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Embedded_Metric_Format_Specification.html

NAMESPACE = "CloudTrain"
SERVICE = "job-events-monitor"
_EMF = {  # observation name -> (EMF metric name, unit, extra dimension key or None)
    "events": ("JobEvents", "Count", "EventType"),
    "queue_wait_seconds": ("QueueWaitSeconds", "Seconds", None),
    "run_seconds": ("RunSeconds", "Seconds", "Result"),
    "lag_seconds": ("EventLagSeconds", "Seconds", None),
}


def emf_line(outcome: Outcome, now: datetime) -> dict | None:
    """One EMF record for a counted event (None for duplicates and invalid messages)."""
    if outcome.kind != "counted":
        return None
    record: dict = {"Service": SERVICE, "JobId": outcome.event["job_id"]}
    directives: list[dict] = []
    for seen in outcome.observations:
        if seen.name not in _EMF:
            continue
        name, unit, extra = _EMF[seen.name]
        record[name] = seen.value
        dims = ["Service"]
        if extra == "EventType":
            record["EventType"] = seen.labels["event_type"]
            dims.append("EventType")
        elif extra == "Result":
            record["Result"] = seen.labels["result"]
            dims.append("Result")
        directives.append(
            {"Namespace": NAMESPACE, "Dimensions": [dims], "Metrics": [{"Name": name, "Unit": unit}]}
        )
    record["_aws"] = {"Timestamp": int(now.timestamp() * 1000), "CloudWatchMetrics": directives}
    return record


def emf_text(outcome: Outcome, now: datetime) -> str | None:
    record = emf_line(outcome, now)
    return json.dumps(record, separators=(",", ":")) if record else None
