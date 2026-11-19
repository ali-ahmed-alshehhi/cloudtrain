"""The Scheduler places a job: SCHEDULED, hand to the worker, RUNNING, delete the message."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.capacity import CapacityTracker
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


class FakeSqs:
    """One message waiting on training-jobs."""

    def __init__(self, messages: list[dict]) -> None:
        self.messages = [{"Body": json.dumps(m), "ReceiptHandle": f"r{i}"} for i, m in enumerate(messages)]
        self.deleted: list[str] = []

    def get_queue_url(self, QueueName):
        return {"QueueUrl": f"http://localstack:4566/000000000000/{QueueName}"}

    def receive_message(self, **kwargs):
        return {"Messages": [self.messages.pop(0)]} if self.messages else {}

    def delete_message(self, QueueUrl, ReceiptHandle):
        self.deleted.append(ReceiptHandle)


class FakeServices:
    """Training Jobs and the worker."""

    def __init__(self, job_answers=(200, 200), worker_answers=(202,), statuses=None) -> None:
        self.job_answers = list(job_answers)
        self.worker_answers = list(worker_answers)
        self.statuses = statuses or {}  # job_id -> status answered by GET /internal/jobs/{id}
        self.calls: list[tuple[str, dict]] = []
        self.status_reads: list[str] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            job_id = request.url.path.rsplit("/", 1)[-1]
            self.status_reads.append(job_id)
            if job_id not in self.statuses:
                return httpx.Response(404, json={})
            return httpx.Response(200, json={"job_id": job_id, "status": self.statuses[job_id]})
        body = json.loads(request.content)
        self.calls.append((request.url.path, body))
        if request.url.host == "training-worker":
            return httpx.Response(self.worker_answers.pop(0), json={})
        return httpx.Response(self.job_answers.pop(0), json={})


def make_app(sqs, services, capacity=None):
    return create_app(
        sqs=sqs,
        transport=httpx.MockTransport(services.handle),
        start_loop=False,
        capacity=capacity,
    )


def test_health():
    with TestClient(make_app(FakeSqs([]), FakeServices())) as client:
        assert client.get("/health").json() == {"status": "ok", "service": "scheduler"}


def test_places_a_job_and_deletes_the_message():
    sqs, services = FakeSqs([FORM]), FakeServices()

    make_app(sqs, services).state.scheduler.read_queue_once()

    steps = [(path, body.get("status")) for path, body in services.calls]
    assert steps == [
        ("/internal/jobs/job-01/status", "SCHEDULED"),
        ("/internal/run", None),
        ("/internal/jobs/job-01/status", "RUNNING"),
    ]
    assert services.calls[1][1] == FORM
    assert sqs.deleted == ["r0"]


def test_cancelled_job_is_dropped_without_starting_the_worker():
    sqs, services = FakeSqs([FORM]), FakeServices(job_answers=[409])

    make_app(sqs, services).state.scheduler.read_queue_once()

    assert [path for path, _ in services.calls] == ["/internal/jobs/job-01/status"]
    assert sqs.deleted == ["r0"]


@pytest.mark.parametrize("job_answer", [500, 503])
def test_message_is_kept_when_training_jobs_is_unhappy(job_answer):
    sqs, services = FakeSqs([FORM]), FakeServices(job_answers=[job_answer])

    make_app(sqs, services).state.scheduler.read_queue_once()

    assert sqs.deleted == []


def test_job_rejected_when_capacity_full():
    """When capacity is already full, the message stays on the queue."""
    cap = CapacityTracker(max_workers=1)
    cap.reserve("job-00", "local-cpu")  # fill the only slot

    sqs = FakeSqs([FORM])
    services = FakeServices(statuses={"job-00": "RUNNING"})  # job-00 is still running
    make_app(sqs, services, capacity=cap).state.scheduler.read_queue_once()

    assert services.calls == []  # never reported to job-service nor handed to the worker
    assert services.status_reads == ["job-00"]  # only asked whether job-00 had ended
    assert sqs.deleted == []  # message stays for retry


def test_capacity_released_on_cancel():
    """When job-service says 409, the capacity slot is freed."""
    cap = CapacityTracker(max_workers=1)
    sqs = FakeSqs([FORM])
    services = FakeServices(job_answers=[409])

    app = make_app(sqs, services, capacity=cap)
    app.state.scheduler.read_queue_once()

    assert cap.active_count == 0  # slot was released
    assert sqs.deleted == ["r0"]


def test_capacity_released_on_error():
    """When job-service returns 500, the capacity slot is freed."""
    cap = CapacityTracker(max_workers=1)
    sqs = FakeSqs([FORM])
    services = FakeServices(job_answers=[500])

    app = make_app(sqs, services, capacity=cap)
    app.state.scheduler.read_queue_once()

    assert cap.active_count == 0
    assert sqs.deleted == []


def test_metrics_endpoint_has_scheduler_gauges():
    """GET /metrics includes the scheduler-specific metrics."""
    sqs, services = FakeSqs([FORM]), FakeServices()
    app = make_app(sqs, services)

    # Place a job so the counter increments
    app.state.scheduler.read_queue_once()

    with TestClient(app) as client:
        resp = client.get("/metrics")
        assert resp.status_code == 200
        body = resp.text
        assert "scheduler_jobs_placed_total" in body
        assert "scheduler_workers_busy" in body
        assert "scheduler_gpus_in_use" in body


def test_gpu_quota_blocks_job():
    """A GPU job is rejected when it would exceed the GPU quota."""
    import os

    old_env = os.environ.get("ENVIRONMENT")
    os.environ["ENVIRONMENT"] = "cloud"
    try:
        cap = CapacityTracker(max_workers=10, max_gpus=1)
        cap.reserve("job-00", "g4dn.xlarge")  # 1 GPU, quota full

        gpu_form = {**FORM, "job_id": "job-01", "resources": {"gpu_count": 1, "cpu_cores": 2, "memory_gb": 4}}
        sqs = FakeSqs([gpu_form])
        services = FakeServices(statuses={"job-00": "RUNNING"})  # job-00 still holds the GPU
        make_app(sqs, services, capacity=cap).state.scheduler.read_queue_once()

        assert services.calls == []
        assert sqs.deleted == []
    finally:
        if old_env is None:
            os.environ.pop("ENVIRONMENT", None)
        else:
            os.environ["ENVIRONMENT"] = old_env


# ---------- slots are freed when a job ends or is retried (GET /internal/jobs/{id}, #102) ----------


def placed(services):
    return [body["job_id"] for path, body in services.calls if path == "/internal/run"]


def test_a_finished_job_frees_its_slot_for_the_next_one():
    sqs = FakeSqs([FORM, {**FORM, "job_id": "job-02"}])
    services = FakeServices(
        job_answers=(200,) * 4, worker_answers=(202, 202), statuses={"job-01": "SUCCEEDED"}
    )
    scheduler = make_app(sqs, services).state.scheduler
    scheduler.read_queue_once()
    scheduler.read_queue_once()
    assert placed(services) == ["job-01", "job-02"]


def test_a_retried_job_is_placed_again():
    """Training Jobs retried job-01 (its worker died): status QUEUED again, same job_id on the queue."""
    sqs = FakeSqs([FORM, FORM])
    services = FakeServices(job_answers=(200,) * 4, worker_answers=(202, 202), statuses={"job-01": "QUEUED"})
    scheduler = make_app(sqs, services).state.scheduler
    scheduler.read_queue_once()
    scheduler.read_queue_once()
    assert placed(services) == ["job-01", "job-01"]


def test_a_running_job_keeps_its_slot():
    sqs = FakeSqs([FORM, {**FORM, "job_id": "job-02"}])
    services = FakeServices(job_answers=(200,) * 4, worker_answers=(202, 202), statuses={"job-01": "RUNNING"})
    scheduler = make_app(sqs, services).state.scheduler
    scheduler.read_queue_once()
    scheduler.read_queue_once()
    assert placed(services) == ["job-01"]  # job-02 waits on the queue


def test_job_service_is_asked_only_when_a_slot_is_needed():
    sqs = FakeSqs([FORM])
    services = FakeServices(job_answers=(200,) * 2, worker_answers=(202,))
    make_app(sqs, services).state.scheduler.read_queue_once()
    assert services.status_reads == []  # there was room: no question asked


def test_an_unreachable_worker_frees_the_slot():
    """Found in the live failure demo: the worker was killed, the hand-over raised ConnectError, the slot
    stayed reserved, and the retried job (and every job after it) waited for capacity forever."""

    class WorkerDown(FakeServices):
        def handle(self, request):
            if request.url.host == "training-worker":
                raise httpx.ConnectError("worker is down", request=request)
            return super().handle(request)

    sqs = FakeSqs([FORM])
    services = WorkerDown(job_answers=(200,) * 2)
    scheduler = make_app(sqs, services).state.scheduler
    scheduler.read_queue_once()

    assert scheduler.capacity.active_count == 0  # the slot is free again
    assert sqs.deleted == []  # the message stays, so the job is placed when the worker is back


# ---------- worker routing (#41): jobs go to the right worker URL ----------


def test_worker_routing_uses_per_machine_url():
    """When TRAINING_WORKER_URLS maps a machine type, the scheduler posts to that URL."""
    import os

    old_env = os.environ.get("ENVIRONMENT")
    old_urls = os.environ.get("TRAINING_WORKER_URLS")
    os.environ["ENVIRONMENT"] = "cloud"
    os.environ["TRAINING_WORKER_URLS"] = json.dumps({"g4dn.xlarge": "http://gpu-lb:8010"})
    try:
        gpu_form = {
            **FORM,
            "job_id": "job-gpu",
            "resources": {"gpu_count": 1, "cpu_cores": 2, "memory_gb": 4},
        }

        class RoutingServices(FakeServices):
            def handle(self, request):
                if request.method == "GET":
                    return super().handle(request)
                body = json.loads(request.content)
                self.calls.append((str(request.url), body))
                if "gpu-lb" in str(request.url) or "training-worker" in str(request.url):
                    return httpx.Response(self.worker_answers.pop(0), json={})
                return httpx.Response(self.job_answers.pop(0), json={})

        sqs = FakeSqs([gpu_form])
        services = RoutingServices(job_answers=(200, 200), worker_answers=(202,))
        app = create_app(sqs=sqs, transport=httpx.MockTransport(services.handle), start_loop=False)
        app.state.scheduler.read_queue_once()

        worker_calls = [url for url, _ in services.calls if "gpu-lb" in url]
        assert len(worker_calls) == 1
        assert "/internal/run" in worker_calls[0]
    finally:
        if old_env is None:
            os.environ.pop("ENVIRONMENT", None)
        else:
            os.environ["ENVIRONMENT"] = old_env
        if old_urls is None:
            os.environ.pop("TRAINING_WORKER_URLS", None)
        else:
            os.environ["TRAINING_WORKER_URLS"] = old_urls


def test_worker_routing_falls_back_to_default():
    """A machine type not in TRAINING_WORKER_URLS uses the default TRAINING_WORKER_URL."""
    import os

    old_urls = os.environ.get("TRAINING_WORKER_URLS")
    os.environ["TRAINING_WORKER_URLS"] = json.dumps({"g4dn.xlarge": "http://gpu-lb:8010"})
    try:
        sqs = FakeSqs([FORM])  # FORM has gpu_count=0 -> local-cpu -> not in TRAINING_WORKER_URLS
        services = FakeServices(job_answers=(200, 200), worker_answers=(202,))
        app = create_app(sqs=sqs, transport=httpx.MockTransport(services.handle), start_loop=False)
        app.state.scheduler.read_queue_once()

        worker_calls = [path for path, _ in services.calls if "/internal/run" in path]
        assert len(worker_calls) == 1
        assert sqs.deleted == ["r0"]
    finally:
        if old_urls is None:
            os.environ.pop("TRAINING_WORKER_URLS", None)
        else:
            os.environ["TRAINING_WORKER_URLS"] = old_urls
