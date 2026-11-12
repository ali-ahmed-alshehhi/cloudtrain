"""The Training Jobs stand-in keeps the contract. Keep these tests passing when you replace it."""

from datetime import timedelta

import httpx
from fastapi.testclient import TestClient

from app.common import now_utc
from app.main import create_app
from tests.conftest import FORM, USER, report, submit


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "service": "job-service"}


def test_submit_answers_202_and_queues_the_full_form(client, queues, check):
    job = submit(client)

    check(job, "Job")
    assert job["status"] == "QUEUED"
    [message] = queues.sent["training-jobs"]
    check(message, "training-job.schema.json")  # the queue carries the shared job form
    assert message["job_id"] == job["job_id"]


def test_ddp_world_size_must_match_gpu_count(client, check):
    form = {**FORM, "parallelism": {"strategy": "ddp", "world_size": 4}}

    response = client.post("/jobs", json=form, headers=USER)

    assert response.status_code == 422
    check(response.json(), "Error")


def test_missing_dataset_version_is_404(client, queues):
    response = client.post("/jobs", json={**FORM, "dataset_version": 7}, headers=USER)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DATASET_VERSION_NOT_FOUND"
    assert queues.sent["training-jobs"] == []


def test_datasets_service_down_is_503(queues):
    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    with TestClient(create_app(queues, httpx.MockTransport(refuse), start_watchdog=False)) as client:
        assert client.post("/jobs", json=FORM, headers=USER).status_code == 503


def test_same_idempotency_key_queues_only_once(client, queues):
    headers = {**USER, "Idempotency-Key": "submit-1"}

    first = submit(client, headers=headers)
    second = submit(client, headers=headers)

    assert first == second
    assert len(queues.sent["training-jobs"]) == 1


def test_happy_path_events_and_cost(client, queues, check):
    job_id = submit(client)["job_id"]

    assert report(client, job_id, "SCHEDULED", machine_type="local-cpu").status_code == 200
    assert report(client, job_id, "RUNNING").status_code == 200
    beat = client.post(
        f"/internal/jobs/{job_id}/heartbeat", json={"worker_id": "w1", "sent_at": "2026-11-14T10:00:00Z"}
    )
    check(beat.json(), "HeartbeatAck")
    done = report(client, job_id, "SUCCEEDED", reported_by="worker")

    assert done.json()["status"] == "SUCCEEDED"
    check(done.json(), "Job")
    feed = client.get("/jobs/events", headers=USER).json()
    check(feed, "EventList")
    for event in feed["items"]:
        check(event, "events/job-event.schema.json")
    assert [e["event_type"] for e in feed["items"]] == [
        "job.queued",
        "job.scheduled",
        "job.running",
        "job.succeeded",
    ]
    assert [e["event_type"] for e in queues.sent["job-events"]][-1] == "job.succeeded"


def test_alert_feed_after(client):
    job_id = submit(client)["job_id"]
    first_page = client.get("/jobs/events", headers=USER).json()
    report(client, job_id, "SCHEDULED")

    newer = client.get(f"/jobs/events?after={first_page['last_event_id']}", headers=USER).json()

    assert [e["event_type"] for e in newer["items"]] == ["job.scheduled"]


def test_steps_out_of_order_are_409(client, check):
    job_id = submit(client)["job_id"]

    response = report(client, job_id, "SUCCEEDED")

    assert response.status_code == 409
    check(response.json(), "Error")


def test_cancel_stops_later_reports(client):
    job_id = submit(client)["job_id"]
    report(client, job_id, "SCHEDULED")

    assert client.post(f"/jobs/{job_id}/cancel", headers=USER).json()["status"] == "CANCELLED"
    assert report(client, job_id, "RUNNING").status_code == 409  # the scheduler learns it was cancelled
    beat = client.post(
        f"/internal/jobs/{job_id}/heartbeat", json={"worker_id": "w1", "sent_at": "2026-11-14T10:00:00Z"}
    )
    assert beat.json()["status"] == "CANCELLED"  # a running worker learns it too
    assert client.post(f"/jobs/{job_id}/cancel", headers=USER).status_code == 409


def test_failure_is_retried_then_stays_failed(client, queues):
    job_id = submit(client)["job_id"]  # retry_limit is 1

    for _ in range(2):
        report(client, job_id, "SCHEDULED")
        report(client, job_id, "RUNNING")
        report(client, job_id, "FAILED", reported_by="worker", reason="crashed")

    job = client.get(f"/jobs/{job_id}", headers=USER).json()
    assert job["status"] == "FAILED"
    assert job["attempt"] == 2
    assert len(queues.sent["training-jobs"]) == 2  # the first run and one retry
    assert "job.retrying" in [e["event_type"] for e in queues.sent["job-events"]]


def test_silent_worker_is_failed_by_the_watchdog(client):
    job_id = submit(client)["job_id"]
    report(client, job_id, "SCHEDULED")
    report(client, job_id, "RUNNING")

    client.app.state.check_running_jobs(now_utc() + timedelta(minutes=10))  # 10 minutes of silence

    job = client.get(f"/jobs/{job_id}", headers=USER).json()
    assert job["status"] == "QUEUED"  # failed, then queued again for its retry
    assert job["attempt"] == 2
    assert any("no heartbeat" in (step["reason"] or "") for step in job["history"])


def test_without_login_is_401(client):
    assert client.post("/jobs", json=FORM).status_code == 401
