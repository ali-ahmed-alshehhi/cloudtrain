"""The status steps of contracts/job-states.md, reported by the Scheduler and the worker."""

from tests.conftest import USER, beat, job, report, start, submit


def test_happy_path_and_its_events(client, queues, check):
    job_id = submit(client)["job_id"]

    assert report(client, job_id, "SCHEDULED", machine_type="local-cpu").status_code == 200
    assert report(client, job_id, "RUNNING").status_code == 200
    check(beat(client, job_id), "HeartbeatAck")
    done = report(client, job_id, "SUCCEEDED", reported_by="worker", worker_id="worker-a")

    assert done.json()["status"] == "SUCCEEDED"
    check(done.json(), "Job")
    assert [h["status"] for h in done.json()["history"]] == ["QUEUED", "SCHEDULED", "RUNNING", "SUCCEEDED"]
    assert done.json()["machine_type"] == "local-cpu"
    feed = client.get("/jobs/events", headers=USER).json()
    check(feed, "EventList")
    for event in feed["items"]:
        check(event, "events/job-event.schema.json")
    kinds = [e["event_type"] for e in feed["items"]]
    assert kinds == ["job.queued", "job.scheduled", "job.running", "job.succeeded"]
    assert queues.types()[-1] == "job.succeeded"
    assert feed["items"][1]["data"]["previous_status"] == "QUEUED"


def test_steps_out_of_order_are_409(client, check):
    job_id = submit(client)["job_id"]

    response = report(client, job_id, "SUCCEEDED")

    assert response.status_code == 409
    check(response.json(), "Error")


def test_a_finished_job_takes_no_more_reports(client):
    job_id = submit(client)["job_id"]
    start(client, job_id)
    report(client, job_id, "SUCCEEDED", reported_by="worker")

    assert report(client, job_id, "FAILED", reported_by="worker").status_code == 409


def test_unknown_job_is_404(client, check):
    for response in (
        client.get("/jobs/job-404", headers=USER),
        report(client, "job-404", "SCHEDULED"),
        client.post(
            "/internal/jobs/job-99999999999999/heartbeat",
            json={"worker_id": "w", "sent_at": "2026-11-20T09:00:00Z"},
        ),
    ):
        assert response.status_code == 404
        check(response.json(), "Error")


def test_cancel_stops_later_reports(client):
    job_id = submit(client)["job_id"]
    report(client, job_id, "SCHEDULED")

    assert client.post(f"/jobs/{job_id}/cancel", headers=USER).json()["status"] == "CANCELLED"
    assert report(client, job_id, "RUNNING").status_code == 409  # the scheduler learns it was cancelled
    assert beat(client, job_id)["status"] == "CANCELLED"  # a running worker learns it too
    assert client.post(f"/jobs/{job_id}/cancel", headers=USER).status_code == 409


def test_cancel_a_running_job_closes_its_attempt(client, clock):
    job_id = submit(client)["job_id"]
    start(client, job_id)
    clock.advance(600)

    cancelled = client.post(f"/jobs/{job_id}/cancel", headers=USER).json()

    assert cancelled["finished_at"] == "2026-11-20T09:10:00Z"
    assert cancelled["history"][-1]["reason"] == "cancelled by user-1"


def test_heartbeat_keeps_the_job_alive_and_answers_its_status(client):
    job_id = submit(client)["job_id"]
    start(client, job_id)

    assert beat(client, job_id) == {"job_id": job_id, "status": "RUNNING"}


def test_a_stale_worker_cannot_finish_the_job(client):
    """Once worker-a runs this attempt, a report from another worker is refused."""
    job_id = submit(client)["job_id"]
    start(client, job_id)
    beat(client, job_id, "worker-a")

    stale = report(client, job_id, "SUCCEEDED", reported_by="worker", worker_id="worker-old")

    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "STALE_WORKER"
    assert job(client, job_id)["status"] == "RUNNING"


def test_reported_times_are_never_in_the_future(client, clock):
    job_id = submit(client)["job_id"]
    report(client, job_id, "SCHEDULED")

    running = report(client, job_id, "RUNNING", started_at="2099-01-01T00:00:00Z").json()

    assert running["started_at"] == "2026-11-20T09:00:00Z"
