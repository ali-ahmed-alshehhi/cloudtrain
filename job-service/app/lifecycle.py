"""The life of a job: the state machine of contracts/job-states.md, in one place.

Every status change goes through `change()`, which (in the same database transaction):
  1. sets the new status,
  2. stores an event (the job's history and the alert feed read these),
  3. puts that event in the outbox for the `job-events` queue.

THE OUTBOX. Saving to PostgreSQL and sending to SQS cannot happen "at the same time": if we send
first and the save fails, the Scheduler gets a job that does not exist; if we save first and the
send fails, a job waits in QUEUED for a message that never comes. So queue messages are first saved
in the `outbox` table, in the same transaction as the change itself, and sent right after the commit.
If SQS is down, the watchdog sends them later, in order. Nothing is lost, nothing is invented.
Consumers already ignore an event_id they have seen, so a message sent twice is harmless.

THE WATCHDOG (`sweep()`) runs every JOB_SWEEP_INTERVAL_SECONDS and makes sure that
"a job can never stay RUNNING forever": a job past max_runtime_minutes, or whose worker has been
silent for HEARTBEAT_TIMEOUT_SECONDS, becomes FAILED, and is retried while retry_limit allows.
"""

import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.common import ApiError, iso
from app.db import Attempt, Event, Job, OutboxMessage, aware
from app.metrics import OUTBOX_PENDING, RETRIES, STATUS_CHANGES, WATCHDOG_FAILURES
from app.models import Heartbeat, StatusReport
from app.queues import QUEUE_ERRORS

logger = logging.getLogger("job-service")

# Which reported status may follow which. CANCELLED comes only from POST /jobs/{id}/cancel,
# and FAILED -> QUEUED only from a retry decided here.
ALLOWED_REPORTS = {
    "QUEUED": {"SCHEDULED"},
    "SCHEDULED": {"RUNNING"},
    "RUNNING": {"SUCCEEDED", "FAILED"},
}
CANCELLABLE = {"QUEUED", "SCHEDULED", "RUNNING"}
ALIVE = {"SCHEDULED", "RUNNING"}  # a worker may be sending heartbeats


def event_json(event: Event, job: Job) -> dict:
    """An event as contracts/events/job-event.schema.json."""
    return {
        "event_id": event.public_id,
        "event_type": event.event_type,
        "job_id": job.public_id,
        "project_id": event.project_id,
        "occurred_at": iso(aware(event.occurred_at)),
        "data": event.data,
    }


class Lifecycle:
    def __init__(self, clock: Callable[[], datetime], heartbeat_timeout_seconds: float) -> None:
        self.clock = clock
        self.heartbeat_timeout = heartbeat_timeout_seconds

    # ---------- building blocks ----------

    @staticmethod
    def enqueue(session: Session, queue: str, body: dict, now: datetime) -> None:
        session.add(OutboxMessage(queue=queue, body=body, created_at=now, tries=0))

    def change(
        self, session: Session, job: Job, status: str, reason: str | None, event_type: str | None = None
    ) -> None:
        now = self.clock()
        previous = None if not job.events else job.status
        job.status = status
        job.updated_at = now
        event = Event(
            project_id=job.project_id,
            event_type=event_type or f"job.{status.lower()}",
            occurred_at=now,
            data={
                "status": status,
                "previous_status": previous,
                "reason": reason,
                "machine_type": job.machine_type,
                "attempt": job.attempt,
            },
        )
        job.events.append(event)
        session.flush()  # gives the event its number (event-N)
        self.enqueue(session, "job-events", event_json(event, job), now)
        STATUS_CHANGES.labels(status).inc()

    def _clamp(self, moment: datetime | None, not_before: datetime | None = None) -> datetime:
        """A reported time, but never in the future and never before `not_before`."""
        now = self.clock()
        moment = min(aware(moment) or now, now)
        if not_before is not None:
            moment = max(moment, aware(not_before))
        return moment

    @staticmethod
    def current_attempt(job: Job) -> Attempt:
        return job.attempts[-1]

    # ---------- what the outside world asks for ----------

    def submit(self, session: Session, project_id: str, user_id: str, spec: dict) -> Job:
        now = self.clock()
        job = Job(
            project_id=project_id,
            submitted_by=user_id,
            spec=spec,
            status="QUEUED",
            attempt=1,
            created_at=now,
            updated_at=now,
            dlq_requeues=0,
        )
        session.add(job)
        session.flush()  # gives the job its number (job-N)
        job.attempts.append(Attempt(number=1))
        self.enqueue(session, "training-jobs", job.form(), now)
        self.change(session, job, "QUEUED", None)
        return job

    def report(self, session: Session, job: Job, report: StatusReport) -> None:
        """A status report from the Scheduler or the worker. 409 if the step is not allowed."""
        if report.status not in ALLOWED_REPORTS.get(job.status, set()):
            raise ApiError(
                409,
                "INVALID_STATUS_TRANSITION",
                f"Job {job.public_id} is {job.status}; it cannot become {report.status}",
            )
        if report.worker_id and job.worker_id and report.worker_id != job.worker_id:
            # A worker from an earlier attempt (e.g. one we declared dead) must not finish this one.
            raise ApiError(
                409,
                "STALE_WORKER",
                f"Job {job.public_id} attempt {job.attempt} runs on {job.worker_id}, not {report.worker_id}",
            )
        attempt = self.current_attempt(job)
        if report.machine_type:
            job.machine_type = attempt.machine_type = report.machine_type
        if report.worker_id and report.status == "RUNNING":
            job.worker_id = attempt.worker_id = report.worker_id

        if report.status == "SCHEDULED":
            self.change(session, job, "SCHEDULED", report.reason)
        elif report.status == "RUNNING":
            started = self._clamp(report.started_at)
            job.started_at = attempt.started_at = started
            job.last_heartbeat_at = self.clock()  # the silence clock starts now
            self.change(session, job, "RUNNING", report.reason)
        elif report.status == "SUCCEEDED":
            self._end_attempt(job, "SUCCEEDED", self._clamp(report.finished_at, job.started_at), None)
            self.change(session, job, "SUCCEEDED", report.reason)
        else:  # FAILED
            reason = report.reason or f"the {report.reported_by} reported a failure"
            self.fail(session, job, reason, self._clamp(report.finished_at, job.started_at))

    def heartbeat(self, job: Job, beat: Heartbeat) -> str:
        """Record "I am still alive". Returns the status the worker must see (CANCELLED = stop)."""
        if job.status in ALIVE:
            if job.worker_id is None:  # the first beat of this attempt tells us which worker runs it
                job.worker_id = self.current_attempt(job).worker_id = beat.worker_id
            if job.worker_id == beat.worker_id:
                job.last_heartbeat_at = self.clock()
            else:
                logger.warning(
                    "heartbeat from %s ignored: attempt %s runs on %s",
                    beat.worker_id,
                    job.attempt,
                    job.worker_id,
                    extra={"job_id": job.public_id},
                )
        return job.status

    def cancel(self, session: Session, job: Job, user_id: str) -> None:
        if job.status not in CANCELLABLE:
            raise ApiError(
                409,
                "JOB_ALREADY_FINISHED",
                f"Job {job.public_id} is {job.status} and cannot be cancelled",
            )
        if job.started_at is not None:  # a machine was running it: close the attempt for the cost
            self._end_attempt(job, "CANCELLED", self.clock(), f"cancelled by {user_id}")
        self.change(session, job, "CANCELLED", f"cancelled by {user_id}")

    # ---------- failure, retry and the watchdog ----------

    def _end_attempt(self, job: Job, outcome: str, at: datetime, reason: str | None) -> None:
        attempt = self.current_attempt(job)
        attempt.finished_at = job.finished_at = at
        attempt.outcome = outcome
        attempt.reason = reason[:1000] if reason else None

    def fail(self, session: Session, job: Job, reason: str, at: datetime) -> None:
        """RUNNING -> FAILED, then FAILED -> QUEUED if retry_limit allows, else a report to the DLQ."""
        self._end_attempt(job, "FAILED", at, reason)
        self.change(session, job, "FAILED", reason)
        retry_limit = int(job.spec["execution"]["retry_limit"])
        retries_used = job.attempt - 1
        if retries_used < retry_limit:
            self._retry(session, job, retry_limit)
        else:
            self.enqueue(
                session,
                "training-jobs-dlq",
                {
                    "kind": "job_failure_report",
                    "job_id": job.public_id,
                    "project_id": job.project_id,
                    "attempts": job.attempt,
                    "reason": reason,
                    "failed_at": iso(at),
                    "form": job.form(),
                },
                self.clock(),
            )
            logger.warning(
                "job failed for good after %s attempts: %s",
                job.attempt,
                reason,
                extra={"job_id": job.public_id},
            )

    def _retry(self, session: Session, job: Job, retry_limit: int) -> None:
        job.attempt += 1
        job.machine_type = job.worker_id = None
        job.started_at = job.finished_at = job.last_heartbeat_at = None
        job.attempts.append(Attempt(number=job.attempt))
        self.enqueue(session, "training-jobs", job.form(), self.clock())
        self.change(
            session, job, "QUEUED", f"retry {job.attempt - 1} of {retry_limit}", event_type="job.retrying"
        )
        RETRIES.inc()

    def sweep(self, session: Session) -> int:
        """End every RUNNING job that is past its time limit or whose worker went silent."""
        now = self.clock()
        silence_limit = timedelta(seconds=self.heartbeat_timeout)
        running = session.scalars(
            select(Job).where(Job.status == "RUNNING").order_by(Job.id).with_for_update(skip_locked=True)
        ).all()
        ended = 0
        for job in running:
            started = aware(job.started_at) or aware(job.updated_at)
            minutes = int(job.spec["execution"]["max_runtime_minutes"])
            last_sign_of_life = aware(job.last_heartbeat_at) or started
            if now - started >= timedelta(minutes=minutes):
                WATCHDOG_FAILURES.labels("time_limit").inc()
                self.fail(session, job, f"time limit of {minutes} minutes passed", now)
            elif now - last_sign_of_life > silence_limit:
                WATCHDOG_FAILURES.labels("heartbeat").inc()
                silent = int((now - last_sign_of_life).total_seconds())
                worker = job.worker_id or "the worker"
                reason = f"no heartbeat for {silent} seconds ({worker} stopped answering)"
                self.fail(session, job, reason, now)
            else:
                continue
            ended += 1
        return ended


def publish_outbox(sessions: sessionmaker, queues, clock: Callable[[], datetime], limit: int = 100) -> int:
    """Send saved queue messages, oldest first. Stops at the first failure to keep the order."""
    sent = 0
    with sessions() as session:
        waiting = session.scalars(
            select(OutboxMessage)
            .where(OutboxMessage.sent_at.is_(None))
            .order_by(OutboxMessage.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).all()
        for message in waiting:
            try:
                queues.send(message.queue, message.body)
            except QUEUE_ERRORS as error:
                message.tries += 1
                message.last_error = str(error)[:500]
                logger.warning("queue %s not reachable; will retry: %s", message.queue, error)
                break
            message.sent_at = clock()
            sent += 1
        session.commit()
        OUTBOX_PENDING.set(
            session.scalar(
                select(func.count()).select_from(OutboxMessage).where(OutboxMessage.sent_at.is_(None))
            )
        )
    return sent
