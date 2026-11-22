"""What the monitor learns from one job event. Pure Python: no queue, no Prometheus, easy to test.

The `job-events` queue is at least once (Training Jobs sends through an outbox), so the same event can
arrive twice and events can arrive out of order. The tracker:
- checks each message against contracts/events/job-event.schema.json,
- ignores an event_id it has already handled (the schema asks every consumer to),
- times each ATTEMPT of a job (a retry is a new attempt, see contracts/job-states.md):
    queue wait = QUEUED (job.queued / job.retrying) -> RUNNING
    run time   = RUNNING -> SUCCEEDED / FAILED / CANCELLED
  whichever order the two events arrive in,
- measures the lag: when we received the event minus when it happened.

Timings live in memory. A restart forgets the attempts in flight (their durations are not measured);
counts are not affected. This is stated in docs/EVALUATION.md.
"""

import json
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from jsonschema import Draft202012Validator

TERMINAL = {"job.succeeded": "SUCCEEDED", "job.failed": "FAILED", "job.cancelled": "CANCELLED"}
QUEUED_EVENTS = {"job.queued", "job.retrying"}
INVALID_REASONS = ("not_json", "schema", "bad_time")


@dataclass(frozen=True)
class Observation:
    """One number to record: name (see app/metrics.py), value, and labels."""

    name: str
    value: float
    labels: dict = field(default_factory=dict)


@dataclass
class Outcome:
    """What happened to one message. kind: counted | duplicate | invalid."""

    kind: str
    reason: str | None = None
    event: dict | None = None
    observations: list[Observation] = field(default_factory=list)


@dataclass
class _Attempt:
    queued: datetime | None = None
    running: datetime | None = None
    ended: datetime | None = None
    result: str | None = None
    waited: bool = False  # queue wait already recorded
    ran: bool = False  # run time already recorded
    touched: datetime | None = None


def parse_time(text: str) -> datetime:
    """ISO 8601 with a zone ('Z' or +00:00) to an aware datetime; ValueError otherwise."""
    moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise ValueError("occurred_at has no time zone")
    return moment.astimezone(UTC)


class Tracker:
    def __init__(
        self,
        schema: dict,
        remember_events: int = 50_000,
        remember_attempts: int = 10_000,
        forget_after: timedelta = timedelta(hours=24),
    ) -> None:
        self.validator = Draft202012Validator(schema)
        self.event_types = tuple(schema["properties"]["event_type"]["enum"])  # from the contract
        self.seen: OrderedDict[str, None] = OrderedDict()
        self.attempts: OrderedDict[tuple[str, int], _Attempt] = OrderedDict()
        self.remember_events = remember_events
        self.remember_attempts = remember_attempts
        self.forget_after = forget_after

    @classmethod
    def from_file(cls, path: str, **options) -> "Tracker":
        with open(path, encoding="utf-8") as file:
            return cls(json.load(file), **options)

    # ---------- one message ----------

    def handle(self, body: str | bytes | dict, received_at: datetime) -> Outcome:
        event, problem = self._read(body)
        if problem:
            return Outcome("invalid", reason=problem)
        if event["event_id"] in self.seen:
            self.seen.move_to_end(event["event_id"])
            return Outcome("duplicate", event=event)
        self._remember(event["event_id"])

        occurred = parse_time(event["occurred_at"])
        observations = [Observation("events", 1, {"event_type": event["event_type"]})]
        if event["event_type"] == "job.retrying":
            observations.append(Observation("retries", 1))
        lag = (received_at - occurred).total_seconds()
        observations.append(Observation("lag_seconds", max(lag, 0.0)))
        observations += self._time_attempt(event, occurred, received_at)
        self._forget_old(received_at)
        return Outcome("counted", event=event, observations=observations)

    def _read(self, body) -> tuple[dict | None, str | None]:
        if isinstance(body, bytes):
            body = body.decode("utf-8", errors="replace")
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except ValueError:
                return None, "not_json"
        errors = sorted(self.validator.iter_errors(body), key=lambda e: list(e.path))
        if errors:
            return None, "schema"
        try:
            parse_time(body["occurred_at"])
        except ValueError:
            return None, "bad_time"
        return body, None

    def _remember(self, event_id: str) -> None:
        self.seen[event_id] = None
        while len(self.seen) > self.remember_events:
            self.seen.popitem(last=False)

    # ---------- timing an attempt ----------

    def _time_attempt(self, event: dict, occurred: datetime, now: datetime) -> list[Observation]:
        key = (event["job_id"], int(event["data"]["attempt"]))
        attempt = self.attempts.get(key) or _Attempt()
        self.attempts[key] = attempt
        self.attempts.move_to_end(key)
        attempt.touched = now

        kind = event["event_type"]
        if kind in QUEUED_EVENTS:
            attempt.queued = occurred
        elif kind == "job.running":
            attempt.running = occurred
        elif kind in TERMINAL:
            attempt.ended = occurred
            attempt.result = TERMINAL[kind]

        found = []
        if not attempt.waited and attempt.queued and attempt.running:
            attempt.waited = True
            wait = (attempt.running - attempt.queued).total_seconds()
            if wait >= 0:
                found.append(Observation("queue_wait_seconds", wait))
        if not attempt.ran and attempt.running and attempt.ended:
            attempt.ran = True
            run = (attempt.ended - attempt.running).total_seconds()
            if run >= 0:
                found.append(Observation("run_seconds", run, {"result": attempt.result}))
        return found

    def _forget_old(self, now: datetime) -> None:
        while self.attempts:
            key, oldest = next(iter(self.attempts.items()))
            too_many = len(self.attempts) > self.remember_attempts
            too_old = oldest.touched and now - oldest.touched > self.forget_after
            if not (too_many or too_old):
                break
            del self.attempts[key]
