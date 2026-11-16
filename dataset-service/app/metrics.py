"""Prometheus metrics, served at GET /metrics."""

from prometheus_client import Counter, Histogram

REQUESTS = Counter(
    "dataset_service_requests_total",
    "Requests handled by the Datasets service",
    ["method", "endpoint", "status"],
)
DURATION = Histogram(
    "dataset_service_request_duration_seconds",
    "Time to answer a request",
    ["endpoint"],
)
