"""Prometheus metrics, served at GET /metrics."""

from prometheus_client import Counter, Histogram

REQUESTS = Counter(
    "gateway_requests_total",
    "Requests handled by the gateway",
    ["route", "method", "status"],
)
DURATION = Histogram(
    "gateway_request_duration_seconds",
    "Time to answer a request, including the service behind the gateway",
    ["route"],
)
