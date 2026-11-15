"""Test helpers: an in-memory database, fake queues, fake Projects and Datasets services, a clock
the tests can move forward, and checks against the contracts.

Unit tests use SQLite instead of PostgreSQL so they run in seconds with nothing else installed.
SQLite has no schemas, so the `jobs` schema is mapped away. The real PostgreSQL path (migrations
included) is covered by `make up` and the integration tests.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import yaml
from botocore.exceptions import EndpointConnectionError
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.background import read_dead_letters_once, watchdog_once
from app.db import SCHEMA, Base
from app.main import create_app
from app.pricing import Pricing
from app.settings import Settings

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"
USER = {"X-User-Id": "user-1"}  # member of project-01
OTHER = {"X-User-Id": "user-2"}  # member of project-02 only
SETTINGS = Settings(heartbeat_interval_seconds=30, heartbeat_timeout_seconds=120, dlq_max_requeues=2)

FORM = {
    "project_id": "project-01",
    "dataset_id": "dataset-01",
    "dataset_version": 1,
    "model": "resnet18",
    "hyperparameters": {"epochs": 10, "batch_size": 32, "learning_rate": 0.001},
    "resources": {"gpu_count": 2, "cpu_cores": 8, "memory_gb": 32},
    "parallelism": {"strategy": "ddp", "world_size": 2},
    "execution": {"max_runtime_minutes": 120, "retry_limit": 1},
}


class Clock:
    """Time that only moves when a test says so."""

    def __init__(self) -> None:
        self.now = datetime(2026, 11, 20, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class FakeQueues:
    """Records what would have been sent to SQS; `down = True` makes every call fail."""

    def __init__(self) -> None:
        self.sent: dict[str, list[dict]] = {"training-jobs": [], "job-events": [], "training-jobs-dlq": []}
        self.inbox: list[dict] = []  # messages waiting on training-jobs-dlq for us to read
        self.deleted: list[str] = []
        self.hidden: list[tuple[str, int]] = []
        self.down = False

    def _check(self) -> None:
        if self.down:
            raise EndpointConnectionError(endpoint_url="http://localstack:4566")

    def send(self, queue: str, body: dict) -> None:
        self._check()
        self.sent[queue].append(json.loads(json.dumps(body)))  # as it would travel: plain JSON

    def receive(self, queue: str, wait_seconds: int) -> list[dict]:
        self._check()
        found, self.inbox = self.inbox, []
        return found

    def delete(self, queue: str, receipt: str) -> None:
        self.deleted.append(receipt)

    def hide(self, queue: str, receipt: str, seconds: int) -> None:
        self.hidden.append((receipt, seconds))

    def ready(self) -> bool:
        return not self.down

    def types(self) -> list[str]:
        return [e["event_type"] for e in self.sent["job-events"]]


PROJECTS = {"project-01": {"user-1"}, "project-02": {"user-2"}}
DATASETS = {"dataset-01": ("project-01", {1}), "dataset-02": ("project-02", {1})}


def fake_services(request: httpx.Request) -> httpx.Response:
    """Projects: project-01 (user-1), project-02 (user-2). Datasets: one per project, version 1."""
    user, parts = request.headers.get("x-user-id"), request.url.path.strip("/").split("/")
    missing = httpx.Response(404, json={"error": {"code": "NOT_FOUND", "message": "no", "request_id": "x"}})
    if parts == ["projects"]:
        mine = [{"project_id": p} for p, members in PROJECTS.items() if user in members]
        return httpx.Response(200, json={"items": mine})
    if parts[0] == "projects":
        if parts[1] not in PROJECTS:
            return missing
        if user not in PROJECTS[parts[1]]:
            refused = {"error": {"code": "NOT_A_MEMBER", "message": "no", "request_id": "x"}}
            return httpx.Response(403, json=refused)
        return httpx.Response(200, json={"project_id": parts[1]})
    if parts[0] == "datasets" and parts[1] in DATASETS:
        project, versions = DATASETS[parts[1]]
        if len(parts) == 2:
            return httpx.Response(200, json={"dataset_id": parts[1], "project_id": project})
        if int(parts[3]) in versions:
            return httpx.Response(200, json={"dataset_id": parts[1], "version": int(parts[3])})
    return missing


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    ).execution_options(schema_translate_map={SCHEMA: None})
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def queues() -> FakeQueues:
    return FakeQueues()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def make_client(engine, queues, clock):
    """make_client(transport=...) builds the app; the background loops are run by the tests."""

    def build(transport=None):
        app = create_app(
            engine=engine,
            queues=queues,
            transport=transport or httpx.MockTransport(fake_services),
            settings=SETTINGS,
            pricing=Pricing.from_file(CONTRACTS / "pricing.yaml"),
            clock=clock,
            start_background=False,
        )
        return TestClient(app)

    return build


@pytest.fixture
def client(make_client):
    with make_client() as test_client:
        yield test_client


@pytest.fixture(scope="session")
def check():
    """check(body, "Job") against the OpenAPI contract, or check(body, "training-job.schema.json")."""
    components = yaml.safe_load((CONTRACTS / "openapi" / "job-service.yaml").read_text())["components"]

    def matches(body: dict, name: str) -> None:
        if name.endswith(".json"):
            schema = json.loads((CONTRACTS / name).read_text())
        else:
            schema = {"$ref": f"#/components/schemas/{name}", "components": components}
        Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(body)

    return matches


# ---------- small helpers so each test reads like the story it checks ----------


def submit(client, form=None, headers=USER) -> dict:
    response = client.post("/jobs", json=form or FORM, headers=headers)
    assert response.status_code == 202, response.text
    return response.json()


def report(client, job_id: str, status: str, **extra):
    body = {"status": status, "reported_by": "scheduler", **extra}
    return client.post(f"/internal/jobs/{job_id}/status", json=body)


def beat(client, job_id: str, worker_id: str = "worker-a") -> dict:
    body = {"worker_id": worker_id, "sent_at": "2026-11-20T09:00:00Z"}
    response = client.post(f"/internal/jobs/{job_id}/heartbeat", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def start(client, job_id: str, machine_type: str = "g4dn.12xlarge") -> None:
    """The Scheduler places the job and reports it running."""
    assert report(client, job_id, "SCHEDULED", machine_type=machine_type).status_code == 200
    assert report(client, job_id, "RUNNING").status_code == 200


def sweep(client) -> int:
    """One round of the watchdog (what the background thread does every few seconds)."""
    state = client.app.state
    return watchdog_once(state.sessions, state.queues, state.lifecycle)


def read_dlq(client, max_requeues: int = 2) -> int:
    state = client.app.state
    return read_dead_letters_once(state.sessions, state.queues, state.lifecycle, 0, max_requeues)


def job(client, job_id: str) -> dict:
    return client.get(f"/jobs/{job_id}", headers=USER).json()
