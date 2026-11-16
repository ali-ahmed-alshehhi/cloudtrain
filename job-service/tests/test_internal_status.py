"""GET /internal/jobs/{id}: the Scheduler reads where a job stands, to free its machine slot (#102)."""

from tests.conftest import report, start, submit, sweep


def status(client, job_id):
    return client.get(f"/internal/jobs/{job_id}")  # no X-User-Id: the Scheduler has no user


def test_shows_status_attempt_and_machine_without_a_user(client, check):
    job_id = submit(client)["job_id"]
    start(client, job_id, machine_type="local-cpu")

    answer = status(client, job_id)

    assert answer.status_code == 200
    check(answer.json(), "InternalJobStatus")
    assert answer.json() == {
        "job_id": job_id,
        "status": "RUNNING",
        "attempt": 1,
        "machine_type": "local-cpu",
        "updated_at": "2026-11-20T09:00:00Z",
    }


def test_a_finished_job_tells_the_scheduler_to_free_the_slot(client):
    job_id = submit(client)["job_id"]
    start(client, job_id)
    report(client, job_id, "SUCCEEDED", reported_by="worker")

    assert status(client, job_id).json()["status"] == "SUCCEEDED"


def test_a_retry_shows_a_new_attempt(client, clock):
    """The same job_id comes back on the queue: the changed attempt tells the Scheduler it is a retry."""
    job_id = submit(client)["job_id"]
    start(client, job_id)
    clock.advance(121)
    sweep(client)  # silent worker: FAILED, then QUEUED again as attempt 2

    answer = status(client, job_id).json()

    assert (answer["status"], answer["attempt"], answer["machine_type"]) == ("QUEUED", 2, None)


def test_unknown_job_is_404(client, check):
    for job_id in ("job-404", "job-99999999999999"):
        answer = status(client, job_id)
        assert answer.status_code == 404
        check(answer.json(), "Error")


def test_reading_changes_nothing(client, queues):
    job_id = submit(client)["job_id"]
    events_before = len(queues.sent["job-events"])

    for _ in range(3):
        status(client, job_id)

    assert len(queues.sent["job-events"]) == events_before
    assert client.get(f"/jobs/{job_id}", headers={"X-User-Id": "user-1"}).json()["status"] == "QUEUED"
