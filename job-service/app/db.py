"""Database tables of the Training Jobs service. They all live in the PostgreSQL schema `jobs`.

    jobs              one row per job: its form, current status, machine, heartbeat, attempt
    attempts          one row per run of a job (a retry is a new attempt), for GPU-hours and cost
    events            every status change, oldest first: the job's history AND the alert feed
    outbox            queue messages waiting to be sent (see app/lifecycle.py, "the outbox")
    idempotency_keys  the first answer to a POST /jobs, so a repeat with the same key is done once

docs/database/jobs.md describes them for the team.
"""

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, MetaData, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

SCHEMA = "jobs"


def utc_now() -> datetime:
    return datetime.now(UTC)


def aware(moment: datetime | None) -> datetime | None:
    """SQLite (used by the unit tests) forgets the time zone; every time we store is UTC."""
    if moment is not None and moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    submitted_by: Mapped[str] = mapped_column(String(128))
    spec: Mapped[dict] = mapped_column(JSON)  # the form as submitted (JobSubmission)
    status: Mapped[str] = mapped_column(String(16), index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    machine_type: Mapped[str | None] = mapped_column(String(64))
    worker_id: Mapped[str | None] = mapped_column(String(128))  # the worker running this attempt
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dlq_requeues: Mapped[int] = mapped_column(Integer, default=0)

    attempts: Mapped[list["Attempt"]] = relationship(order_by="Attempt.number", lazy="selectin")
    events: Mapped[list["Event"]] = relationship(order_by="Event.id", lazy="selectin")

    @property
    def public_id(self) -> str:
        """The ID the outside world sees, e.g. 104 -> "job-104", 7 -> "job-07"."""
        return f"job-{self.id:02d}"

    def form(self) -> dict:
        """The full training job form for the queue (contracts/training-job.schema.json)."""
        return {"job_id": self.public_id, **self.spec}


class Attempt(Base):
    """One run of a job on one machine. GPU-hours and cost are the sum over all attempts,
    because a failed attempt still used (and paid for) its machine."""

    __tablename__ = "attempts"

    job_id: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.jobs.id"), primary_key=True)
    number: Mapped[int] = mapped_column(Integer, primary_key=True)
    machine_type: Mapped[str | None] = mapped_column(String(64))
    worker_id: Mapped[str | None] = mapped_column(String(128))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str | None] = mapped_column(String(16))  # SUCCEEDED, FAILED, CANCELLED
    reason: Mapped[str | None] = mapped_column(String(1000))


class Event(Base):
    __tablename__ = "events"
    # The alert feed asks "events of these projects after event N": one index answers it.
    __table_args__ = (Index("ix_events_project_id_id", "project_id", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.jobs.id"), index=True)
    project_id: Mapped[str] = mapped_column(String(64))
    event_type: Mapped[str] = mapped_column(String(32))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    data: Mapped[dict] = mapped_column(JSON)

    @property
    def public_id(self) -> str:
        return f"event-{self.id}"


class OutboxMessage(Base):
    __tablename__ = "outbox"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    queue: Mapped[str] = mapped_column(String(64))
    body: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    tries: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_keys"

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    job_id: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.jobs.id"))
    response_body: Mapped[dict] = mapped_column(JSON)  # the first answer, returned again on a repeat
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
