"""Feature freeze (#19): the failure paths no other test reached.

Other services broken, rule-breaking forms, the database down, two identical submits at the same
instant, the background loops surviving a crash, every error in the shared format, and the SQS code
itself (with botocore's Stubber, so no real AWS is needed).
"""

import json
import time

import httpx
import pytest
from botocore.exceptions import EndpointConnectionError
from botocore.stub import Stubber
from sqlalchemy import update
from sqlalchemy.exc import OperationalError

from app.background import start_loops
from app.db import IdempotencyRecord, OutboxMessage
from app.queues import Queues
from app.settings import Settings
from tests.conftest import FORM, USER, fake_services, report, start, submit

ERROR = {"error": {"code": "BOOM", "message": "broken", "request_id": "x"}}


def answering(path_start: str, status: int):
    """The fake services, except that paths starting with `path_start` answer `status`."""

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith(path_start):
            return httpx.Response(status, json=ERROR)
        return fake_services(request)

    return httpx.MockTransport(handle)


# ---------- the other services are broken ----------


@pytest.mark.parametrize(
    ("broken", "method", "path"),
    [
        ("/projects/", "post", "/jobs"),  # membership check
        ("/projects", "get", "/jobs/events"),  # the list of my projects (alert feed)
        ("/datasets/dataset-01", "post", "/jobs"),  # the dataset itself
        ("/datasets/dataset-01/versions", "post", "/jobs"),  # the version check
    ],
)
def test_a_server_error_elsewhere_becomes_503(make_client, check, broken, method, path):
    with make_client(answering(broken, 500)) as client:
        response = client.request(method, path, json=FORM if method == "post" else None, headers=USER)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
    check(response.json(), "Error")


def test_datasets_refusing_the_user_is_403(make_client, queues):
    with make_client(answering("/datasets/dataset-01", 403)) as client:
        response = client.post("/jobs", json=FORM, headers=USER)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NOT_A_MEMBER"
    assert queues.sent["training-jobs"] == []


# ---------- forms that break the rules ----------


@pytest.mark.parametrize(
    "parallelism",
    [
        {"strategy": "single", "world_size": 2},  # single means one process
        {"strategy": "ddp", "world_size": 1},  # DDP needs at least two
    ],
)
def test_parallelism_must_fit_the_strategy(client, parallelism):
    form = {**FORM, "parallelism": parallelism}

    assert client.post("/jobs", json=form, headers=USER).status_code == 422


# ---------- the database is down ----------


def test_health_is_503_when_the_database_is_down(make_client, monkeypatch, check):
    with make_client() as client:
        engine = client.app.state.sessions.kw["bind"]

        def refuse(*args, **kwargs):
            raise OperationalError("SELECT 1", {}, Exception("database is down"))

        monkeypatch.setattr(engine, "connect", refuse)
        response = client.get("/health")

    assert response.status_code == 503
    check(response.json(), "Error")


# ---------- two identical submits at the same instant ----------


def test_the_same_key_twice_at_the_same_instant_creates_one_job(client, queues):
    """The other request saves the key between our check and our commit: we answer like it did."""
    headers = {**USER, "Idempotency-Key": "race-1"}
    winner = submit(client, headers={**USER, "Idempotency-Key": "first"})  # an existing job to point at
    lifecycle = client.app.state.lifecycle
    real_submit = lifecycle.submit

    def submit_while_the_other_request_wins(session, *args):
        job = real_submit(session, *args)
        with client.app.state.sessions() as other:  # the competing request commits first
            other.add(
                IdempotencyRecord(
                    user_id="user-1",
                    key="race-1",
                    request_fingerprint=_fingerprint(FORM),
                    job_id=int(winner["job_id"].removeprefix("job-")),
                    response_body=winner,
                    created_at=lifecycle.clock(),
                )
            )
            other.commit()
        return job

    lifecycle.submit = submit_while_the_other_request_wins
    try:
        response = client.post("/jobs", json=FORM, headers=headers)
    finally:
        lifecycle.submit = real_submit

    assert response.status_code == 202
    assert response.json() == winner  # the winner's answer, not a second job
    assert len(queues.sent["training-jobs"]) == 1  # our own job was rolled back, never queued


def _fingerprint(form: dict) -> str:
    import hashlib

    from app.models import JobSubmission

    spec = JobSubmission.model_validate(form).model_dump()
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()


# ---------- sending right after the commit fails in an unexpected way ----------


def test_an_unexpected_send_error_does_not_fail_the_submit(client, queues, monkeypatch):
    def explode(body):
        raise RuntimeError("bug in the send code")

    monkeypatch.setattr(queues, "send", lambda queue, body: explode(body))

    response = client.post("/jobs", json=FORM, headers=USER)

    assert response.status_code == 202  # the job is saved; the watchdog sends the message later


# ---------- the background loops ----------


def test_the_loops_send_messages_and_survive_a_crashing_round(make_client, queues, clock, monkeypatch):
    with make_client() as client:
        state = client.app.state
        submit(client)
        queues.sent["training-jobs"].clear()  # pretend the first send never happened...
        with state.sessions() as session:  # ...by marking every message unsent again
            session.execute(update(OutboxMessage).values(sent_at=None))
            session.commit()

        rounds = {"n": 0}
        real_sweep = state.lifecycle.sweep

        def sweep_that_crashes_once(session):
            rounds["n"] += 1
            if rounds["n"] == 1:
                raise RuntimeError("one bad round")
            return real_sweep(session)

        monkeypatch.setattr(state.lifecycle, "sweep", sweep_that_crashes_once)
        stop = start_loops(state.sessions, queues, state.lifecycle, 0, 0.05, 0, 3)
        try:
            deadline = time.time() + 5
            while time.time() < deadline and not (rounds["n"] >= 2 and queues.sent["training-jobs"]):
                clock.advance(1)
                time.sleep(0.05)
        finally:
            stop()

    assert rounds["n"] >= 2, "the watchdog must keep running after a crashing round"
    assert queues.sent["training-jobs"], "the unsent message must be sent by the loop"


# ---------- every error in the shared format ----------


def test_an_unknown_address_is_404_in_the_shared_format(client, check):
    response = client.get("/nothing-here")

    assert response.status_code == 404
    check(response.json(), "Error")


def test_a_wrong_method_is_405_and_lists_the_allowed_ones(client, check):
    job_id = submit(client)["job_id"]

    response = client.delete(f"/jobs/{job_id}", headers=USER)

    assert response.status_code == 405
    assert response.headers["Allow"] == "GET"
    check(response.json(), "Error")


def test_an_unexpected_error_is_500_in_the_shared_format(make_client, check, monkeypatch):
    with make_client() as client:
        monkeypatch.setattr(client.app.state.lifecycle, "submit", lambda *a: 1 / 0)
        client_raise = client.__class__(client.app, raise_server_exceptions=False)
        response = client_raise.post("/jobs", json=FORM, headers=USER)

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    check(response.json(), "Error")


# ---------- settings from the environment ----------


def test_settings_are_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("HEARTBEAT_INTERVAL_SECONDS", "2")
    monkeypatch.setenv("HEARTBEAT_TIMEOUT_SECONDS", "6")
    monkeypatch.setenv("JOB_DLQ_MAX_REQUEUES", "5")
    monkeypatch.setenv("PRICING_FILE", "/tmp/prices.yaml")

    settings = Settings.from_env()

    assert (settings.heartbeat_interval_seconds, settings.heartbeat_timeout_seconds) == (2, 6)
    assert settings.dlq_max_requeues == 5
    assert settings.pricing_file == "/tmp/prices.yaml"


def test_unsafe_heartbeat_settings_stop_the_start(monkeypatch):
    monkeypatch.setenv("HEARTBEAT_INTERVAL_SECONDS", "30")
    monkeypatch.setenv("HEARTBEAT_TIMEOUT_SECONDS", "60")

    with pytest.raises(ValueError, match="at least 3"):
        Settings.from_env()


# ---------- the SQS code (botocore Stubber: the real client, with canned AWS answers) ----------


@pytest.fixture
def real_queues(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("SQS_ENDPOINT", "http://localstack:4566")
    queues = Queues()
    queues._urls = {name: f"http://localstack:4566/000000000000/{name}" for name in queues.names}
    return queues


def test_send_puts_the_body_on_the_queue_as_json(real_queues):
    with Stubber(real_queues.client) as stub:
        stub.add_response(
            "send_message",
            {"MessageId": "m-1"},
            {"QueueUrl": real_queues.url("job-events"), "MessageBody": json.dumps({"event_id": "event-1"})},
        )
        real_queues.send("job-events", {"event_id": "event-1"})
        stub.assert_no_pending_responses()


def test_receive_reads_json_and_keeps_unreadable_bodies_apart(real_queues):
    with Stubber(real_queues.client) as stub:
        stub.add_response(
            "receive_message",
            {
                "Messages": [
                    {"Body": json.dumps({"job_id": "job-01"}), "ReceiptHandle": "r-1"},
                    {"Body": "not json at all", "ReceiptHandle": "r-2"},
                ]
            },
        )
        found = real_queues.receive("training-jobs-dlq", 0)

    assert found[0] == {"body": {"job_id": "job-01"}, "receipt": "r-1"}
    assert found[1]["body"] == {"unreadable": "not json at all"}


def test_delete_and_hide_use_the_receipt(real_queues):
    url = real_queues.url("training-jobs-dlq")
    with Stubber(real_queues.client) as stub:
        stub.add_response("delete_message", {}, {"QueueUrl": url, "ReceiptHandle": "r-1"})
        stub.add_response(
            "change_message_visibility",
            {},
            {"QueueUrl": url, "ReceiptHandle": "r-2", "VisibilityTimeout": 43200},
        )
        real_queues.delete("training-jobs-dlq", "r-1")
        real_queues.hide("training-jobs-dlq", "r-2", 43200)
        stub.assert_no_pending_responses()


def test_ready_is_false_when_sqs_cannot_be_reached(real_queues, monkeypatch):
    real_queues._urls = {}

    def unreachable(**kwargs):
        raise EndpointConnectionError(endpoint_url="http://localstack:4566")

    monkeypatch.setattr(real_queues.client, "get_queue_url", unreachable)

    assert real_queues.ready() is False


def test_ready_looks_queues_up_by_name(real_queues):
    real_queues._urls = {}
    with Stubber(real_queues.client) as stub:
        for name in ("training-jobs", "job-events", "training-jobs-dlq"):
            stub.add_response("get_queue_url", {"QueueUrl": f"http://q/{name}"}, {"QueueName": name})
        assert real_queues.ready() is True


# ---------- a cancel while queued has no machine time ----------


def test_cancelling_a_queued_job_has_no_cost(client):
    job_id = submit(client)["job_id"]

    cancelled = client.post(f"/jobs/{job_id}/cancel", headers=USER).json()

    assert cancelled["status"] == "CANCELLED"
    assert cancelled["finished_at"] is None  # never ran
    assert (cancelled["gpu_hours"], cancelled["estimated_cost_usd"]) == (0, 0)


def test_a_cancelled_running_job_tells_the_worker_to_stop(client):
    job_id = submit(client)["job_id"]
    start(client, job_id)
    client.post(f"/jobs/{job_id}/cancel", headers=USER)

    beat = client.post(
        f"/internal/jobs/{job_id}/heartbeat",
        json={"worker_id": "worker-a", "sent_at": "2026-11-20T09:00:00Z"},
    ).json()

    assert beat["status"] == "CANCELLED"
    assert report(client, job_id, "SUCCEEDED", reported_by="worker").status_code == 409
