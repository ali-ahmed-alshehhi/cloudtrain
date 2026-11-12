"""The worker stand-in: one job at a time, heartbeats, SUCCEEDED, and stops when cancelled."""

import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app

FORM = {
    "job_id": "job-01",
    "project_id": "project-01",
    "dataset_id": "dataset-01",
    "dataset_version": 1,
    "model": "resnet18",
    "hyperparameters": {"epochs": 1, "batch_size": 32, "learning_rate": 0.001},
    "resources": {"gpu_count": 0, "cpu_cores": 2, "memory_gb": 4},
    "parallelism": {"strategy": "single", "world_size": 1},
    "execution": {"max_runtime_minutes": 10, "retry_limit": 0},
}


class FakeJobService:
    def __init__(self, job_status="RUNNING") -> None:
        self.job_status = job_status
        self.calls: list[tuple[str, dict]] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.calls.append((request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={"job_id": "job-01", "status": self.job_status})


@pytest.fixture(autouse=True)
def quick_training(monkeypatch):
    monkeypatch.setenv("STANDIN_TRAINING_SECONDS", "0.3")
    monkeypatch.setenv("HEARTBEAT_INTERVAL_SECONDS", "0.1")


def wait_until_idle(app) -> None:
    for _ in range(50):
        if app.state.worker.busy.acquire(blocking=False):
            app.state.worker.busy.release()
            return
        time.sleep(0.05)
    raise AssertionError("the worker never finished")


def test_health():
    with TestClient(create_app(httpx.MockTransport(FakeJobService().handle))) as client:
        assert client.get("/health").json() == {"status": "ok", "service": "training-worker"}


def test_runs_with_heartbeats_then_reports_success():
    job_service = FakeJobService()
    app = create_app(httpx.MockTransport(job_service.handle))
    with TestClient(app) as client:
        response = client.post("/internal/run", json=FORM)
        wait_until_idle(app)

    assert response.status_code == 202
    paths = [path for path, _ in job_service.calls]
    assert paths.count("/internal/jobs/job-01/heartbeat") >= 2
    assert paths[-1] == "/internal/jobs/job-01/status"
    assert job_service.calls[-1][1]["status"] == "SUCCEEDED"


def test_second_job_while_busy_is_409():
    app = create_app(httpx.MockTransport(FakeJobService().handle))
    with TestClient(app) as client:
        client.post("/internal/run", json=FORM)
        second = client.post("/internal/run", json={**FORM, "job_id": "job-02"})
        wait_until_idle(app)

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "WORKER_BUSY"


def test_stops_without_reporting_when_cancelled():
    job_service = FakeJobService(job_status="CANCELLED")
    app = create_app(httpx.MockTransport(job_service.handle))
    with TestClient(app) as client:
        client.post("/internal/run", json=FORM)
        wait_until_idle(app)

    assert [path for path, _ in job_service.calls] == ["/internal/jobs/job-01/heartbeat"]


def test_bad_form_is_422():
    with TestClient(create_app(httpx.MockTransport(FakeJobService().handle))) as client:
        assert client.post("/internal/run", json={**FORM, "job_id": "104"}).status_code == 422
