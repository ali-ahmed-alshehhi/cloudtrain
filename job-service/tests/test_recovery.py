"""A job can never stay RUNNING forever: silent workers, time limits, retries and the DLQ report.

These are the unit-level version of tests/integration/test_failure_recovery.py (the final demo).
"""

from tests.conftest import FORM, beat, job, report, start, submit, sweep


def events(client, job_id):
    return client.get(f"/jobs/{job_id}/events", headers={"X-User-Id": "user-1"}).json()["items"]


def test_silent_worker_fails_the_job_and_it_is_retried(client, queues, clock, check):
    job_id = submit(client)["job_id"]
    start(client, job_id)
    beat(client, job_id)

    clock.advance(119)
    assert sweep(client) == 0  # still inside HEARTBEAT_TIMEOUT_SECONDS
    clock.advance(2)
    assert sweep(client) == 1

    found = job(client, job_id)
    assert found["status"] == "QUEUED"
    assert found["attempt"] == 2
    assert found["machine_type"] is None  # the next attempt may land on another machine
    kinds = [e["event_type"] for e in events(client, job_id)]
    assert kinds[-2:] == ["job.failed", "job.retrying"]
    failed, retrying = events(client, job_id)[-2:]
    assert "heartbeat" in failed["data"]["reason"]  # what the failure-recovery demo checks
    assert retrying["data"]["attempt"] == 2
    for event in events(client, job_id):
        check(event, "events/job-event.schema.json")
    assert [m["job_id"] for m in queues.sent["training-jobs"]] == [job_id, job_id]  # back in the queue


def test_retried_job_finishes_on_its_second_attempt(client, clock):
    job_id = submit(client)["job_id"]
    start(client, job_id)
    clock.advance(121)
    sweep(client)

    start(client, job_id)
    beat(client, job_id, "worker-b")
    done = report(client, job_id, "SUCCEEDED", reported_by="worker", worker_id="worker-b").json()

    assert done["status"] == "SUCCEEDED"
    assert max(e["data"]["attempt"] for e in events(client, job_id)) == 2
    assert [h["status"] for h in done["history"]] == [
        "QUEUED",
        "SCHEDULED",
        "RUNNING",
        "FAILED",
        "QUEUED",
        "SCHEDULED",
        "RUNNING",
        "SUCCEEDED",
    ]


def test_regular_heartbeats_are_never_mistaken_for_a_dead_worker(client, clock):
    job_id = submit(client)["job_id"]
    start(client, job_id)

    for _ in range(20):  # 10 minutes of beats every 30 seconds
        clock.advance(30)
        beat(client, job_id)
        assert sweep(client) == 0

    assert job(client, job_id)["status"] == "RUNNING"


def test_a_worker_that_never_sends_a_heartbeat_is_caught_too(client, clock):
    job_id = submit(client)["job_id"]
    start(client, job_id)  # RUNNING, but not one heartbeat ever arrives

    clock.advance(121)

    assert sweep(client) == 1


def test_time_limit_fails_the_job(client, clock):
    form = {**FORM, "execution": {"max_runtime_minutes": 5, "retry_limit": 0}}
    job_id = submit(client, form)["job_id"]
    start(client, job_id)

    for _ in range(10):  # the worker is alive and well, just too slow
        clock.advance(30)
        beat(client, job_id)
        sweep(client)

    found = job(client, job_id)
    assert found["status"] == "FAILED"
    assert found["history"][-1]["reason"] == "time limit of 5 minutes passed"


def test_retries_used_up_stays_failed_and_reports_to_the_dlq(client, queues, clock, check):
    job_id = submit(client)["job_id"]  # retry_limit 1: two attempts in total
    for _ in range(2):
        start(client, job_id)
        report(client, job_id, "FAILED", reported_by="worker", reason="CUDA out of memory")

    found = job(client, job_id)
    assert found["status"] == "FAILED"
    assert found["attempt"] == 2
    [report_message] = queues.sent["training-jobs-dlq"]
    assert report_message["kind"] == "job_failure_report"
    assert report_message["job_id"] == job_id
    assert report_message["reason"] == "CUDA out of memory"
    check(report_message["form"], "training-job.schema.json")
    assert report(client, job_id, "SCHEDULED").status_code == 409  # FAILED for good is final


def test_a_worker_reported_failure_is_retried(client, queues):
    job_id = submit(client)["job_id"]
    start(client, job_id)

    after = report(client, job_id, "FAILED", reported_by="worker", reason="crashed").json()

    assert after["status"] == "QUEUED"
    assert queues.types()[-2:] == ["job.failed", "job.retrying"]


def test_the_dead_worker_cannot_come_back_and_finish(client, clock):
    """worker-a is declared dead; the retry runs on worker-b; worker-a's late report is refused."""
    job_id = submit(client)["job_id"]
    start(client, job_id)
    beat(client, job_id, "worker-a")
    clock.advance(121)
    sweep(client)
    start(client, job_id)
    beat(client, job_id, "worker-b")

    late = report(client, job_id, "SUCCEEDED", reported_by="worker", worker_id="worker-a")

    assert late.status_code == 409
    assert beat(client, job_id, "worker-a")["status"] == "RUNNING"  # answered, but not counted
    clock.advance(121)
    assert sweep(client) == 1, "worker-a's beats must not keep worker-b's attempt alive"
