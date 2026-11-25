"""Reading training-jobs-dlq: jobs the Scheduler could not handle, and our own failure reports."""

from tests.conftest import beat, job, read_dlq, report, submit


def from_dlq(queues, body, receipt="r-1"):
    queues.inbox.append({"body": body, "receipt": receipt})


def test_a_stuck_queued_job_is_put_back_on_the_queue(client, queues):
    job_id = submit(client)["job_id"]
    [message] = queues.sent["training-jobs"]
    from_dlq(queues, message)  # SQS gave up on it: the Scheduler failed it 3 times

    read_dlq(client)

    assert [m["job_id"] for m in queues.sent["training-jobs"]] == [job_id, job_id]
    assert queues.deleted == ["r-1"]
    assert job(client, job_id)["status"] == "QUEUED"


def test_requeues_stop_after_the_limit(client, queues):
    job_id = submit(client)["job_id"]
    for attempt in range(3):  # the limit in the tests is 2
        from_dlq(queues, {"job_id": job_id}, receipt=f"r-{attempt}")
        read_dlq(client)

    assert len(queues.sent["training-jobs"]) == 1 + 2
    assert queues.deleted == ["r-0", "r-1", "r-2"]


def test_a_message_for_a_job_already_handled_is_dropped(client, queues):
    job_id = submit(client)["job_id"]
    report(client, job_id, "SCHEDULED")
    report(client, job_id, "RUNNING")
    from_dlq(queues, {"job_id": job_id})

    read_dlq(client)

    assert len(queues.sent["training-jobs"]) == 1
    assert queues.deleted == ["r-1"]


def test_unreadable_or_unknown_messages_are_dropped(client, queues):
    from_dlq(queues, {"unreadable": "%%%"}, receipt="r-1")
    from_dlq(queues, {"job_id": "job-77"}, receipt="r-2")

    read_dlq(client)

    assert queues.deleted == ["r-1", "r-2"]


def test_our_failure_reports_stay_on_the_queue(client, queues):
    from_dlq(queues, {"kind": "job_failure_report", "job_id": "job-01"})

    read_dlq(client)

    assert queues.deleted == []
    assert queues.hidden == [("r-1", 12 * 3600)]


def test_a_scheduled_job_whose_hand_offs_all_failed_is_put_back(client, queues):
    """#167: the Scheduler placed it, but no worker answered 3 times, so SQS sent it here."""
    job_id = submit(client)["job_id"]
    report(client, job_id, "SCHEDULED")
    from_dlq(queues, {"job_id": job_id})

    read_dlq(client)

    assert [m["job_id"] for m in queues.sent["training-jobs"]] == [job_id, job_id]
    assert queues.deleted == ["r-1"]
    assert job(client, job_id)["status"] == "SCHEDULED"  # no new state: the contract is unchanged
    # The Scheduler picks the message up again and reports the same attempt: 200, as in #89.
    assert report(client, job_id, "SCHEDULED").status_code == 200


def test_a_scheduled_job_a_worker_already_has_is_not_put_back(client, queues):
    """A heartbeat means a worker took this attempt: sending it again could start it twice."""
    job_id = submit(client)["job_id"]
    report(client, job_id, "SCHEDULED")
    beat(client, job_id)
    from_dlq(queues, {"job_id": job_id})

    read_dlq(client)

    assert len(queues.sent["training-jobs"]) == 1
    assert queues.deleted == ["r-1"]


def test_a_stuck_scheduled_job_also_stops_after_the_limit(client, queues):
    job_id = submit(client)["job_id"]
    report(client, job_id, "SCHEDULED")
    for attempt in range(3):  # the limit in the tests is 2
        from_dlq(queues, {"job_id": job_id}, receipt=f"r-{attempt}")
        read_dlq(client)

    assert len(queues.sent["training-jobs"]) == 1 + 2
    assert job(client, job_id)["status"] == "SCHEDULED"
