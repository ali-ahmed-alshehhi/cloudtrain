"""The worker API and orchestration lifecycle."""

import json
import tempfile
import time
from pathlib import Path

import httpx
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


class FakeDatasetClient:
    def __init__(self) -> None:
        self.folder = tempfile.TemporaryDirectory()

    def download(self, dataset_id: str, version: int) -> Path:
        return Path(self.folder.name)


class FakeTracker:
    def __init__(self) -> None:
        self.params = {}
        self.metrics = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def log_params(self, params):
        self.params.update(params)

    def log_metrics(self, metrics, step=None):
        self.metrics.append((step, metrics))


def successful_trainer(job, dataset_dir, metric_callback, stop_event):
    metric_callback(1, {"loss": 0.4, "accuracy": 0.8})
    return {"loss": 0.4, "accuracy": 0.8}


def make_app(job_service, trainer=successful_trainer, *, runtime_minute_seconds=60):
    return create_app(
        transport=httpx.MockTransport(job_service.handle),
        dataset_client=FakeDatasetClient(),
        trainer=trainer,
        tracker_factory=lambda job: FakeTracker(),
        heartbeat_seconds=0.01,
        runtime_minute_seconds=runtime_minute_seconds,
    )


def wait_until_idle(app) -> None:
    for _ in range(50):
        if app.state.worker.busy.acquire(blocking=False):
            app.state.worker.busy.release()
            return
        time.sleep(0.05)
    raise AssertionError("the worker never finished")


def test_health():
    with TestClient(make_app(FakeJobService())) as client:
        assert client.get("/health").json() == {"status": "ok", "service": "training-worker"}


def test_runs_with_heartbeats_then_reports_success():
    job_service = FakeJobService()
    app = make_app(job_service, trainer=lambda *args: (time.sleep(0.04), {"accuracy": 0.8})[1])
    with TestClient(app) as client:
        response = client.post("/internal/run", json=FORM)
        wait_until_idle(app)

    assert response.status_code == 202
    paths = [path for path, _ in job_service.calls]
    assert paths.count("/internal/jobs/job-01/heartbeat") >= 2
    assert paths[-1] == "/internal/jobs/job-01/status"
    assert job_service.calls[-1][1]["status"] == "SUCCEEDED"


def test_logs_job_parameters_epoch_metrics_and_final_metrics():
    job_service = FakeJobService()
    tracker = FakeTracker()
    app = create_app(
        transport=httpx.MockTransport(job_service.handle),
        dataset_client=FakeDatasetClient(),
        trainer=successful_trainer,
        tracker_factory=lambda job: tracker,
        heartbeat_seconds=0.01,
    )
    with TestClient(app) as client:
        client.post("/internal/run", json=FORM)
        wait_until_idle(app)

    assert tracker.params["model"] == "resnet18"
    assert tracker.params["epochs"] == 1
    assert tracker.metrics == [
        (1, {"loss": 0.4, "accuracy": 0.8}),
        (None, {"final_loss": 0.4, "final_accuracy": 0.8}),
    ]


def test_second_job_while_busy_is_409():
    app = make_app(FakeJobService(), trainer=lambda *args: (time.sleep(0.04), {})[1])
    with TestClient(app) as client:
        client.post("/internal/run", json=FORM)
        second = client.post("/internal/run", json={**FORM, "job_id": "job-02"})
        wait_until_idle(app)

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "WORKER_BUSY"


def test_stops_without_reporting_when_cancelled():
    job_service = FakeJobService(job_status="CANCELLED")
    stopped = []

    def trainer(job, dataset_dir, metric_callback, stop_event):
        while not stop_event.wait(0.005):
            pass
        stopped.append(True)
        return {}

    app = make_app(job_service, trainer=trainer)
    with TestClient(app) as client:
        client.post("/internal/run", json=FORM)
        wait_until_idle(app)

    assert [path for path, _ in job_service.calls] == ["/internal/jobs/job-01/heartbeat"]
    assert stopped == [True]


def test_timeout_reports_failed_once_and_releases_busy_state():
    job_service = FakeJobService()

    def trainer(job, dataset_dir, metric_callback, stop_event):
        stop_event.wait()
        return {}

    app = make_app(job_service, trainer=trainer, runtime_minute_seconds=0.02)
    with TestClient(app) as client:
        assert client.post("/internal/run", json=FORM).status_code == 202
        wait_until_idle(app)
        assert client.post("/internal/run", json={**FORM, "job_id": "job-02"}).status_code == 202
        wait_until_idle(app)

    reports = [body for path, body in job_service.calls if path.endswith("/status")]
    assert len(reports) == 2
    assert all(report["status"] == "FAILED" for report in reports)
    assert all("maximum runtime" in report["reason"] for report in reports)


def test_training_failure_reports_failed_once():
    job_service = FakeJobService()

    def trainer(*args):
        raise RuntimeError("training exploded")

    app = make_app(job_service, trainer=trainer)
    with TestClient(app) as client:
        client.post("/internal/run", json=FORM)
        wait_until_idle(app)

    reports = [body for path, body in job_service.calls if path.endswith("/status")]
    assert len(reports) == 1
    assert reports[0]["status"] == "FAILED"
    assert "training exploded" in reports[0]["reason"]


def test_bad_form_is_422():
    with TestClient(make_app(FakeJobService())) as client:
        assert client.post("/internal/run", json={**FORM, "job_id": "104"}).status_code == 422
