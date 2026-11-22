import json
from datetime import timedelta

import boto3
from botocore.exceptions import EndpointConnectionError
from moto import mock_aws

from app.consumer import Consumer
from app.metrics import emf_line
from app.queue import JobEventsQueue
from tests.conftest import FIXTURE_TWO_ATTEMPTS, Clock, FakeQueue, event, value


def make(queue, tracker, metrics, logger, lines=None, clock=None):
    return Consumer(
        queue,
        tracker,
        metrics,
        logger,
        wait_seconds=0,
        emf=True,
        write=(lines.append if lines is not None else lambda _: None),
        clock=clock or Clock(),
    )


def test_valid_events_are_recorded_then_deleted(tracker, metrics, registry, logger):
    queue = FakeQueue()
    queue.put(*FIXTURE_TWO_ATTEMPTS)
    assert make(queue, tracker, metrics, logger).poll_once() == len(FIXTURE_TWO_ATTEMPTS)
    assert len(queue.deleted) == len(FIXTURE_TWO_ATTEMPTS)
    assert value(registry, "cloudtrain_job_events_total", event_type="job.running") == 2
    assert value(registry, "cloudtrain_job_retries_total") == 1
    assert value(registry, "cloudtrain_job_queue_wait_seconds_count") == 2
    assert value(registry, "cloudtrain_job_queue_wait_seconds_sum") == 40
    assert value(registry, "cloudtrain_job_run_seconds_sum", result="SUCCEEDED") == 300
    assert value(registry, "cloudtrain_job_run_seconds_sum", result="FAILED") == 60
    assert value(registry, "cloudtrain_job_events_last_poll_timestamp_seconds") > 0


def test_duplicates_and_invalid_messages_are_counted_and_deleted(tracker, metrics, registry, logger):
    queue = FakeQueue()
    first = FIXTURE_TWO_ATTEMPTS[0]
    queue.put(first, first, "not json", {"event_id": "event-1"})
    make(queue, tracker, metrics, logger).poll_once()
    assert len(queue.deleted) == 4
    assert value(registry, "cloudtrain_job_events_total", event_type="job.queued") == 1
    assert value(registry, "cloudtrain_job_events_duplicate_total") == 1
    assert value(registry, "cloudtrain_job_events_invalid_total", reason="not_json") == 1
    assert value(registry, "cloudtrain_job_events_invalid_total", reason="schema") == 1


def test_a_message_our_code_fails_on_is_kept(tracker, metrics, logger, monkeypatch):
    queue = FakeQueue()
    queue.put(FIXTURE_TWO_ATTEMPTS[0])

    def broken(*_args):
        raise RuntimeError("bug")

    monkeypatch.setattr(tracker, "handle", broken)
    assert make(queue, tracker, metrics, logger).poll_once() == 0
    assert queue.deleted == [], "not deleted: SQS will show it again"


def test_a_failed_delete_is_counted_and_the_retry_is_a_duplicate(tracker, metrics, registry, logger):
    queue = FakeQueue()
    queue.put(FIXTURE_TWO_ATTEMPTS[0])
    queue.fail_delete = True
    consumer = make(queue, tracker, metrics, logger)
    consumer.poll_once()
    assert value(registry, "cloudtrain_job_events_poll_errors_total") == 1
    queue.fail_delete = False
    queue.put(FIXTURE_TWO_ATTEMPTS[0])
    consumer.poll_once()
    assert value(registry, "cloudtrain_job_events_total", event_type="job.queued") == 1
    assert value(registry, "cloudtrain_job_events_duplicate_total") == 1


def test_queue_down_backs_off_and_health_follows_the_last_read(tracker, metrics, registry, logger):
    down = EndpointConnectionError(endpoint_url="http://localstack:4566")
    queue = FakeQueue([down, down])
    clock = Clock()
    consumer = make(queue, tracker, metrics, logger, clock=clock)
    waits = []
    consumer._stop.wait = lambda seconds: waits.append(seconds) or len(waits) >= 2  # stop after 2 waits
    consumer._stop.is_set = lambda: len(waits) >= 2
    consumer.run()
    assert waits == [1, 2]
    assert value(registry, "cloudtrain_job_events_poll_errors_total") == 2
    assert consumer.is_healthy(120) is False, "never read the queue yet"
    consumer.poll_once()
    assert consumer.is_healthy(120) is True
    clock.now += timedelta(seconds=121)
    assert consumer.is_healthy(120) is False


def test_emf_lines_are_valid_cloudwatch_records(tracker, metrics, logger):
    queue = FakeQueue()
    queue.put(event(1, "job.queued", 0), event(2, "job.running", 30), event(3, "job.succeeded", 90))
    lines = []
    make(queue, tracker, metrics, logger, lines=lines).poll_once()
    assert len(lines) == 3
    last = json.loads(lines[-1])
    directives = last["_aws"]["CloudWatchMetrics"]
    assert isinstance(last["_aws"]["Timestamp"], int)
    for directive in directives:
        assert directive["Namespace"] == "CloudTrain"
        for dims in directive["Dimensions"]:
            assert all(key in last for key in dims), "every dimension is a key of the record"
        for metric in directive["Metrics"]:
            assert isinstance(last[metric["Name"]], (int, float))
    assert last["RunSeconds"] == 60 and last["Result"] == "SUCCEEDED" and last["EventType"] == "job.succeeded"


def test_no_emf_for_duplicates_or_invalid(tracker):
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    assert emf_line(tracker.handle("nope", now), now) is None
    tracker.handle(FIXTURE_TWO_ATTEMPTS[0], now)
    assert emf_line(tracker.handle(FIXTURE_TWO_ATTEMPTS[0], now), now) is None


@mock_aws
def test_real_boto3_calls_against_a_fake_sqs(tracker, metrics, registry, logger):
    client = boto3.client("sqs", region_name="us-east-1")
    url = client.create_queue(QueueName="job-events")["QueueUrl"]
    for item in FIXTURE_TWO_ATTEMPTS[:3]:
        client.send_message(QueueUrl=url, MessageBody=json.dumps(item))  # exactly what Training Jobs sends
    queue = JobEventsQueue("job-events", None, "us-east-1", client=client)
    consumer = make(queue, tracker, metrics, logger)
    handled = 0
    for _ in range(3):  # SQS may return fewer than all messages per call
        handled += consumer.poll_once()
    assert handled == 3
    assert value(registry, "cloudtrain_job_queue_wait_seconds_sum") == 30
    left = client.get_queue_attributes(QueueUrl=url, AttributeNames=["ApproximateNumberOfMessages"])
    assert left["Attributes"]["ApproximateNumberOfMessages"] == "0", "every handled message was deleted"
