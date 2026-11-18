"""Prometheus metrics about jobs (on top of the request metrics in app/common.py).

Hilal + Adel can chart these on the dashboards: how many jobs move, how often workers die,
how often jobs are retried, and whether queue messages are waiting to be sent.
Defined once per process, because Prometheus refuses to register the same name twice.
"""

from prometheus_client import Counter, Gauge

JOBS_SUBMITTED = Counter("job_service_jobs_submitted_total", "Jobs accepted by POST /jobs")
STATUS_CHANGES = Counter(
    "job_service_status_changes_total", "Status changes, by the status reached", ["status"]
)
WATCHDOG_FAILURES = Counter(
    "job_service_watchdog_failures_total",
    "Jobs the watchdog ended, by cause (heartbeat or time_limit)",
    ["cause"],
)
RETRIES = Counter("job_service_retries_total", "Failed jobs put back on the queue")
DEAD_LETTERS = Counter(
    "job_service_dead_letters_total", "Messages read from training-jobs-dlq, by what was done", ["action"]
)
OUTBOX_PENDING = Gauge("job_service_outbox_pending", "Queue messages saved but not sent yet")
