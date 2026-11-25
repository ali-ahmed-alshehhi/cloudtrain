"""Test helpers: FIXTURE job events (made up, never real results), a fake queue and a fake clock.

Every fixture event is checked against contracts/events/job-event.schema.json by test_fixtures_match_contract.
"""

import json
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from prometheus_client import CollectorRegistry

from app.metrics import Metrics
from app.queue import Message
from app.tracker import Tracker

# moto (the fake SQS) needs some credentials; these are fake and never leave the test.
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "contracts" / "events" / "job-event.schema.json"
T0 = datetime(2026, 11, 20, 9, 0, tzinfo=UTC)

_STATUS = {
    "job.queued": ("QUEUED", None),
    "job.scheduled": ("SCHEDULED", "QUEUED"),
    "job.running": ("RUNNING", "SCHEDULED"),
    "job.succeeded": ("SUCCEEDED", "RUNNING"),
    "job.failed": ("FAILED", "RUNNING"),
    "job.cancelled": ("CANCELLED", "QUEUED"),
    "job.retrying": ("QUEUED", "FAILED"),
}


def event(n: int, event_type: str, seconds: float, job: str = "job-104", attempt: int = 1, **data) -> dict:
    """FIXTURE: one job event `seconds` after T0."""
    status, previous = _STATUS[event_type]
    when = (T0 + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")
    machine = "g4dn.xlarge" if event_type not in ("job.queued", "job.retrying") else None
    return {
        "event_id": f"event-{n}",
        "event_type": event_type,
        "job_id": job,
        "project_id": "project-01",
        "occurred_at": when,
        "data": {
            "status": status,
            "previous_status": previous,
            "reason": None,
            "machine_type": machine,
            "attempt": attempt,
            **data,
        },
    }


# FIXTURE: a job that fails once and succeeds on its second attempt.
# Attempt 1: queued 0 s, running 30 s, failed 90 s. Attempt 2: retrying 95 s, running 105 s, succeeded 405 s.
FIXTURE_TWO_ATTEMPTS = [
    event(1, "job.queued", 0),
    event(2, "job.scheduled", 10),
    event(3, "job.running", 30),
    event(4, "job.failed", 90, reason="no heartbeat for 120 seconds"),
    event(5, "job.retrying", 95, attempt=2, reason="retry 1 of 1"),
    event(6, "job.scheduled", 100, attempt=2),
    event(7, "job.running", 105, attempt=2),
    event(8, "job.succeeded", 405, attempt=2),
]


@pytest.fixture
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def tracker(schema) -> Tracker:
    return Tracker(schema)


@pytest.fixture
def registry() -> CollectorRegistry:
    return CollectorRegistry()


@pytest.fixture
def metrics(registry) -> Metrics:
    return Metrics(registry)


@pytest.fixture
def logger() -> logging.Logger:
    return logging.getLogger("job-events-monitor-test")


class FakeQueue:
    """Hands out prepared batches; records deletes. A batch may be an exception to raise."""

    def __init__(self, batches=None) -> None:
        self.batches = list(batches or [])
        self.deleted: list[str] = []
        self.fail_delete = False

    def put(self, *bodies) -> None:
        start = sum(len(b) for b in self.batches if isinstance(b, list))
        self.batches.append(
            [
                Message(b if isinstance(b, str) else json.dumps(b), f"r-{start + i}")
                for i, b in enumerate(bodies)
            ]
        )

    def receive(self, wait_seconds: int):
        if not self.batches:
            return []
        batch = self.batches.pop(0)
        if isinstance(batch, Exception):
            raise batch
        return batch

    def delete(self, receipt: str) -> None:
        if self.fail_delete:
            from botocore.exceptions import EndpointConnectionError

            raise EndpointConnectionError(endpoint_url="http://localstack:4566")
        self.deleted.append(receipt)


class Clock:
    def __init__(self) -> None:
        self.now = T0 + timedelta(seconds=1000)

    def __call__(self) -> datetime:
        return self.now


def value(registry: CollectorRegistry, name: str, **labels) -> float:
    return registry.get_sample_value(name, labels) or 0.0
