"""Cross-check with the real producer.

tests/fixtures/FIXTURE-recorded-from-job-service.json is what Training Jobs (Mariam, job-service on main,
17 Nov 2026) put on job-events when its own test harness ran: submit, start, no heartbeat for 121 s
(FAILED and retried as attempt 2), start again, succeed after 300 s, and a second job cancelled while
queued. FIXTURE: made with a fake clock, not real training or cloud results.
"""

import json
from pathlib import Path

from app.consumer import Consumer
from tests.conftest import Clock, FakeQueue, value

RECORDED = Path(__file__).parent / "fixtures" / "FIXTURE-recorded-from-job-service.json"


def test_real_producer_messages_are_understood(tracker, metrics, registry, logger):
    events = json.loads(RECORDED.read_text(encoding="utf-8"))
    queue = FakeQueue()
    queue.put(*events)
    consumer = Consumer(queue, tracker, metrics, logger, wait_seconds=0, emf=False, clock=Clock())
    assert consumer.poll_once() == len(events)

    assert value(registry, "cloudtrain_job_events_invalid_total", reason="schema") == 0
    types = {e["event_type"] for e in events}
    assert sum(value(registry, "cloudtrain_job_events_total", event_type=t) for t in types) == 10
    assert value(registry, "cloudtrain_job_retries_total") == 1
    # Attempt 1 waited 30 s and ran 121 s until the heartbeat check failed it.
    # Attempt 2 waited 15 s and ran 300 s.
    assert value(registry, "cloudtrain_job_queue_wait_seconds_count") == 2
    assert value(registry, "cloudtrain_job_queue_wait_seconds_sum") == 45
    assert value(registry, "cloudtrain_job_run_seconds_sum", result="FAILED") == 121
    assert value(registry, "cloudtrain_job_run_seconds_sum", result="SUCCEEDED") == 300
    assert value(registry, "cloudtrain_job_run_seconds_count", result="CANCELLED") == 0
