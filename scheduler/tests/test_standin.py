"""The Scheduler stand-in places a job: SCHEDULED, hand to the worker, RUNNING, delete the message."""

import json

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
    """Training Jobs and the worker. `job_answers` are the status codes Training Jobs gives, in order."""

    def __init__(self, job_answers=(200, 200), worker_answers=(202,)) -> None:
        self.job_answers = list(job_answers)
        self.worker_answers = list(worker_answers)
        self.calls: list[tuple[str, dict]] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.calls.append((request.url.path, body))
        if request.url.host == "training-worker":
            return httpx.Response(self.worker_answers.pop(0), json={})
        return httpx.Response(self.job_answers.pop(0), json={})


def make_app(sqs, services):
    return create_app(sqs=sqs, transport=httpx.MockTransport(services.handle), start_loop=False)


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
    assert services.calls[1][1] == FORM  # the worker gets the full job form
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

    assert sqs.deleted == []  # SQS gives the message again later
