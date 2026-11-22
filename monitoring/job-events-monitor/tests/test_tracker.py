import json
from datetime import timedelta

from jsonschema import Draft202012Validator

from app.tracker import Tracker
from tests.conftest import FIXTURE_TWO_ATTEMPTS, T0, event


def observed(outcomes, name):
    return [(o.value, o.labels) for out in outcomes for o in out.observations if o.name == name]


def test_fixtures_match_contract(schema):
    validator = Draft202012Validator(schema)
    for item in [*FIXTURE_TWO_ATTEMPTS, event(9, "job.cancelled", 5, job="job-200")]:
        assert not list(validator.iter_errors(item)), item["event_id"]
    for example in schema["examples"]:
        assert not list(validator.iter_errors(example))


def test_two_attempts_give_wait_and_run_per_attempt(tracker):
    received = T0 + timedelta(seconds=1000)
    outcomes = [tracker.handle(item, received) for item in FIXTURE_TWO_ATTEMPTS]
    assert all(o.kind == "counted" for o in outcomes)
    assert observed(outcomes, "queue_wait_seconds") == [(30.0, {}), (10.0, {})]
    assert observed(outcomes, "run_seconds") == [
        (60.0, {"result": "FAILED"}),
        (300.0, {"result": "SUCCEEDED"}),
    ]
    assert len(observed(outcomes, "retries")) == 1
    types = [labels["event_type"] for _, labels in observed(outcomes, "events")]
    assert types == [item["event_type"] for item in FIXTURE_TWO_ATTEMPTS]


def test_duplicate_event_id_is_ignored(tracker):
    first = tracker.handle(FIXTURE_TWO_ATTEMPTS[0], T0)
    again = tracker.handle(json.dumps(FIXTURE_TWO_ATTEMPTS[0]), T0)
    assert (first.kind, again.kind) == ("counted", "duplicate")
    assert again.observations == []


def test_out_of_order_events_still_time_the_attempt(tracker):
    # RUNNING arrives before QUEUED, and the end arrives before RUNNING.
    ended = tracker.handle(event(3, "job.succeeded", 90), T0)
    running = tracker.handle(event(2, "job.running", 30), T0)
    queued = tracker.handle(event(1, "job.queued", 0), T0)
    assert observed([ended], "run_seconds") == []
    assert observed([running], "run_seconds") == [(60.0, {"result": "SUCCEEDED"})]
    assert observed([queued], "queue_wait_seconds") == [(30.0, {})]


def test_cancelled_while_queued_has_no_run_time(tracker):
    outs = [tracker.handle(event(1, "job.queued", 0), T0), tracker.handle(event(2, "job.cancelled", 20), T0)]
    assert observed(outs, "run_seconds") == [] and observed(outs, "queue_wait_seconds") == []


def test_each_duration_is_recorded_once(tracker):
    outs = [tracker.handle(e, T0) for e in [event(1, "job.queued", 0), event(2, "job.running", 30)]]
    # A second RUNNING event (different id, same attempt) must not record the wait again.
    outs.append(tracker.handle(event(3, "job.running", 40), T0))
    assert observed(outs, "queue_wait_seconds") == [(30.0, {})]


def test_negative_durations_are_skipped(tracker):
    outs = [tracker.handle(event(1, "job.queued", 50), T0), tracker.handle(event(2, "job.running", 10), T0)]
    assert observed(outs, "queue_wait_seconds") == []


def test_lag_is_received_minus_occurred_and_never_negative(tracker):
    late = tracker.handle(event(1, "job.queued", 0), T0 + timedelta(seconds=2.5))
    early = tracker.handle(event(2, "job.scheduled", 10), T0)  # clock skew: received "before" it happened
    assert observed([late], "lag_seconds") == [(2.5, {})]
    assert observed([early], "lag_seconds") == [(0.0, {})]


def test_invalid_messages_are_reported_with_a_reason(tracker):
    assert tracker.handle("not json {", T0).reason == "not_json"
    assert tracker.handle({"hello": "world"}, T0).reason == "schema"
    wrong_type = event(1, "job.queued", 0) | {"event_type": "job.exploded"}
    assert tracker.handle(wrong_type, T0).reason == "schema"
    no_zone = event(2, "job.queued", 0) | {"occurred_at": "2026-11-20T09:00:00"}
    assert tracker.handle(no_zone, T0).reason == "bad_time"
    assert tracker.seen == {}, "invalid messages are not remembered as seen"


def test_memory_is_bounded(schema):
    small = Tracker(schema, remember_events=3, remember_attempts=2, forget_after=timedelta(hours=1))
    for n in range(1, 6):
        small.handle(event(n, "job.queued", 0, job=f"job-{n}"), T0)
    assert list(small.seen) == ["event-3", "event-4", "event-5"]
    assert [key[0] for key in small.attempts] == ["job-4", "job-5"]
    small.handle(event(6, "job.queued", 0, job="job-6"), T0 + timedelta(hours=2))
    assert [key[0] for key in small.attempts] == ["job-6"], (
        "attempts untouched for over an hour are forgotten"
    )
