"""The two background loops of the Training Jobs service.

1. The watchdog, every few seconds: sends waiting outbox messages and runs `Lifecycle.sweep()`
   (time limits and silent workers).
2. The dead-letter reader, on `training-jobs-dlq` (this service is its only reader). Two kinds of
   messages land there:
   - a job form that SQS moved there because the Scheduler could not handle it SQS_MAX_RECEIVE_COUNT
     times (for example the Scheduler was down). If the job is still QUEUED it would wait forever,
     so it is put back on `training-jobs`, at most JOB_DLQ_MAX_REQUEUES times. After that it is
     logged as an error and stays QUEUED: the user can cancel it. (Marking it FAILED would need a
     new status step, QUEUED -> FAILED: not now, see docs/decisions/0007-job-service-design.md.)
   - our own failure report for a job whose retries are used up (contracts/job-states.md). It is
     left on the queue for people and the queue-depth alarm, and hidden from us for 12 hours.

Several copies of the service may run (ECS). Each job row is locked while it changes
(SELECT ... FOR UPDATE SKIP LOCKED), so two copies never change the same job at once.
"""

import logging
import threading
from collections.abc import Callable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db import Job
from app.lifecycle import Lifecycle, publish_outbox
from app.metrics import DEAD_LETTERS
from app.queues import QUEUE_ERRORS

logger = logging.getLogger("job-service")
DLQ = "training-jobs-dlq"
HIDE_REPORT_SECONDS = 12 * 3600  # the longest SQS allows
MAX_DB_ID = 2**31 - 1


def job_number(job_id: object) -> int | None:
    """ "job-104" -> 104; anything else -> None."""
    if not isinstance(job_id, str) or not job_id.startswith("job-"):
        return None
    digits = job_id.removeprefix("job-")
    if not digits.isdigit() or int(digits) > MAX_DB_ID:
        return None
    return int(digits)


def watchdog_once(sessions: sessionmaker, queues, lifecycle: Lifecycle) -> int:
    with sessions() as session:
        ended = lifecycle.sweep(session)
        session.commit()
    publish_outbox(sessions, queues, lifecycle.clock)
    return ended


def waiting_for_a_worker(job: Job) -> bool:
    """True if no worker has this job yet, so putting its message back on the queue is safe.

    QUEUED: the Scheduler never placed it. SCHEDULED with no worker and no heartbeat: the
    Scheduler placed it, but every hand-off to a worker failed (#167). Its message goes back
    and the job stays SCHEDULED: the Scheduler reports SCHEDULED again (200, contract #89)
    and retries the hand-off. If a worker took it meanwhile, that report gets 409 and the
    Scheduler drops the message, so a job never runs twice.
    """
    if job.status == "QUEUED":
        return True
    return job.status == "SCHEDULED" and job.worker_id is None and job.last_heartbeat_at is None


def read_dead_letters_once(
    sessions: sessionmaker, queues, lifecycle: Lifecycle, wait_seconds: int, max_requeues: int
) -> int:
    handled = 0
    for message in queues.receive(DLQ, wait_seconds):
        body, receipt = message["body"], message["receipt"]
        if body.get("kind") == "job_failure_report":
            queues.hide(DLQ, receipt, HIDE_REPORT_SECONDS)
            DEAD_LETTERS.labels("kept_failure_report").inc()
            continue

        number = job_number(body.get("job_id"))
        action = "dropped_unknown"
        with sessions() as session:
            job = session.scalar(select(Job).where(Job.id == number).with_for_update()) if number else None
            if job is not None and not waiting_for_a_worker(job):
                action = "dropped_already_handled"  # cancelled or picked up meanwhile
            elif job is not None and job.dlq_requeues < max_requeues:
                job.dlq_requeues += 1
                lifecycle.enqueue(session, "training-jobs", job.form(), lifecycle.clock())
                action = "requeued"
                logger.warning(
                    "job came back from the dead-letter queue; queued again (%s of %s)",
                    job.dlq_requeues,
                    max_requeues,
                    extra={"job_id": job.public_id},
                )
            elif job is not None:
                action = "gave_up"
                logger.error(
                    "job could not be scheduled after %s tries; it stays %s until cancelled",
                    max_requeues,
                    job.status,
                    extra={"job_id": job.public_id},
                )
            session.commit()
        queues.delete(DLQ, receipt)
        DEAD_LETTERS.labels(action).inc()
        handled += 1
    if handled:
        publish_outbox(sessions, queues, lifecycle.clock)
    return handled


def start_loops(
    sessions: sessionmaker,
    queues,
    lifecycle: Lifecycle,
    sweep_seconds: float,
    outbox_seconds: float,
    dlq_wait_seconds: int,
    dlq_max_requeues: int,
) -> Callable[[], None]:
    """Start both loops in background threads. Returns a function that stops them."""
    stop = threading.Event()

    def watchdog() -> None:
        last_sweep: datetime | None = None
        while not stop.is_set():
            try:
                now = lifecycle.clock()
                if last_sweep is None or (now - last_sweep).total_seconds() >= sweep_seconds:
                    with sessions() as session:
                        lifecycle.sweep(session)
                        session.commit()
                    last_sweep = now
                publish_outbox(sessions, queues, lifecycle.clock)
            except Exception:  # never let the watchdog die: log and try again
                logger.exception("watchdog round failed")
            stop.wait(outbox_seconds)

    def dead_letters() -> None:
        while not stop.is_set():
            try:
                read_dead_letters_once(sessions, queues, lifecycle, dlq_wait_seconds, dlq_max_requeues)
            except QUEUE_ERRORS:
                logger.warning("dead-letter queue not reachable; trying again in 5 seconds")
                stop.wait(5)
            except Exception:
                logger.exception("dead-letter round failed")
                stop.wait(5)

    threading.Thread(target=watchdog, daemon=True, name="watchdog").start()
    threading.Thread(target=dead_letters, daemon=True, name="dead-letter-reader").start()
    return stop.set
