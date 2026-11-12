"""Prometheus metrics, served at GET /metrics."""

from prometheus_client import Counter, Histogram

REQUESTS = Counter(
    "project_service_requests_total",
    "Requests handled by the Projects service",
    ["method", "endpoint", "status"],
)
DURATION = Histogram(
    "project_service_request_duration_seconds",
    "Time to answer a request",
    ["endpoint"],
)
