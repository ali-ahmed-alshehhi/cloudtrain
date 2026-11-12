"""Test helpers: fake queues, a fake Datasets service, and contract checks."""

import json
from pathlib import Path

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from app.main import create_app

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"
USER = {"X-User-Id": "user-1"}

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


class FakeQueues:
    """Records what would have been sent to SQS."""

    def __init__(self) -> None:
        self.sent: dict[str, list[dict]] = {"training-jobs": [], "job-events": []}

    def send(self, queue: str, body: dict) -> None:
        self.sent[queue].append(json.loads(json.dumps(body)))  # as it would travel: plain JSON

    def ready(self) -> bool:
        return True


def fake_datasets(request: httpx.Request) -> httpx.Response:
    """Only dataset-01 version 1 exists."""
    if request.url.path == "/datasets/dataset-01/versions/1":
        return httpx.Response(200, json={"dataset_id": "dataset-01", "version": 1})
    return httpx.Response(404, json={"error": {"code": "NOT_FOUND", "message": "no", "request_id": "x"}})


@pytest.fixture
def queues() -> FakeQueues:
    return FakeQueues()


@pytest.fixture
def client(queues):
    app = create_app(queues=queues, transport=httpx.MockTransport(fake_datasets), start_watchdog=False)
    with TestClient(app) as test_client:
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


def submit(client, form=None, headers=USER) -> dict:
    response = client.post("/jobs", json=form or FORM, headers=headers)
    assert response.status_code == 202, response.text
    return response.json()


def report(client, job_id: str, status: str, **extra):
    body = {"status": status, "reported_by": "scheduler", **extra}
    return client.post(f"/internal/jobs/{job_id}/status", json=body)
