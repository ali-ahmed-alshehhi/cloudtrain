"""The loop that reads job-events: receive, handle, record, delete.

- A valid event, a duplicate and an invalid message are all deleted after they are recorded
  (an invalid message would otherwise come back forever; it is counted and logged instead).
- If OUR code fails on a message, it is NOT deleted: SQS shows it again later.
- If the queue cannot be reached, the loop waits 1, 2, 4 ... up to 30 seconds and tries again.
"""

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime

from app.metrics import Metrics, emf_text
from app.queue import QUEUE_ERRORS, JobEventsQueue
from app.tracker import Tracker

MAX_BACKOFF_SECONDS = 30


def utc_now() -> datetime:
    return datetime.now(UTC)


class Consumer:
    def __init__(
        self,
        queue: JobEventsQueue,
        tracker: Tracker,
        metrics: Metrics,
        logger: logging.Logger,
        wait_seconds: int = 20,
        emf: bool = True,
        write: Callable[[str], None] = print,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.queue = queue
        self.tracker = tracker
        self.metrics = metrics
        self.logger = logger
        self.wait_seconds = wait_seconds
        self.emf = emf
        self.write = write
        self.clock = clock
        self.last_success: datetime | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ---------- one round ----------

    def poll_once(self) -> int:
        """Read one batch. Returns how many messages were handled. Raises QUEUE_ERRORS."""
        messages = self.queue.receive(self.wait_seconds)
        self.last_success = self.clock()
        self.metrics.last_poll.set(self.last_success.timestamp())
        handled = 0
        for message in messages:
            if self._handle(message):
                handled += 1
        self.metrics.attempts_tracked.set(len(self.tracker.attempts))
        return handled

    def _handle(self, message) -> bool:
        now = self.clock()
        try:
            outcome = self.tracker.handle(message.body, now)
        except Exception:  # our bug: keep the message so it is not lost
            self.logger.exception("could not handle a job event; it stays on the queue")
            return False
        self.metrics.record(outcome)
        if outcome.kind == "invalid":
            self.logger.warning(f"invalid job event deleted ({outcome.reason})")
        elif self.emf:
            line = emf_text(outcome, now)
            if line:
                self.write(line)
        try:
            self.queue.delete(message.receipt)
        except QUEUE_ERRORS:
            # It comes back later; the event_id check then ignores it.
            self.metrics.poll_errors.inc()
            self.logger.warning("could not delete a job event; it will be seen again")
        return True

    # ---------- the background loop ----------

    def run(self) -> None:
        backoff = 1
        while not self._stop.is_set():
            try:
                self.poll_once()
                backoff = 1
            except QUEUE_ERRORS as error:
                self.metrics.poll_errors.inc()
                self.logger.warning(f"job-events queue unavailable ({type(error).__name__})")
                self._stop.wait(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
            except Exception:
                self.metrics.poll_errors.inc()
                self.logger.exception("unexpected error while polling job-events")
                self._stop.wait(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)

    def start(self) -> None:
        self._thread = threading.Thread(target=self.run, name="job-events-consumer", daemon=True)
        self._thread.start()

    def stop(self, timeout: float | None = None) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout)

    def is_healthy(self, within_seconds: int) -> bool:
        """Healthy = the queue was read successfully in the last `within_seconds`."""
        if self.last_success is None:
            return False
        return (self.clock() - self.last_success).total_seconds() <= within_seconds
