"""The Training Jobs service (owner: Mariam, Student 3). Port 8003, internal.

It owns the LIFE of every training job, from POST /jobs to a final status (not the training itself):
    - POST /jobs checks the form, checks project membership (Projects) and that the dataset version
      exists in the same project (Datasets), saves the job in PostgreSQL as QUEUED, answers 202 at once
      and puts the full form on `training-jobs`
    - follows the status steps of contracts/job-states.md; a step that is not allowed gets 409
    - every change is stored as an event (history + alert feed) and published to `job-events`
    - cancel; heartbeats; a watchdog fails a job whose worker went silent or that passed its time
      limit; a failed job is retried while retry_limit allows, then reported to `training-jobs-dlq`
    - gpu_hours and estimated_cost_usd from contracts/pricing.yaml, over every attempt

Run with:  uvicorn --factory app.main:create_app --port 8003
How the pieces fit: app/lifecycle.py (state machine, outbox, watchdog), app/background.py (loops),
app/clients.py (Projects and Datasets), app/pricing.py (cost), app/db.py (tables).
"""

import hashlib
import json
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi import Path as PathParam
from fastapi.responses import JSONResponse
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.background import MAX_DB_ID, job_number, start_loops
from app.clients import Services
from app.common import ApiError, current_user, iso, now_utc, setup_service
from app.db import Event, IdempotencyRecord, Job, aware
from app.lifecycle import Lifecycle, event_json, publish_outbox
from app.metrics import JOBS_SUBMITTED
from app.models import Heartbeat, JobSubmission, StatusReport
from app.pricing import Pricing
from app.queues import Queues
from app.settings import Settings

SERVICE_NAME = "job-service"
JobIdPath = Annotated[str, PathParam(pattern=r"^job-[0-9]+$")]
UserDep = Annotated[str, Depends(current_user)]


def create_app(
    engine: Engine | None = None,
    queues=None,
    transport: httpx.BaseTransport | None = None,
    settings: Settings | None = None,
    pricing: Pricing | None = None,
    clock: Callable[[], datetime] = now_utc,
    start_background: bool = True,
) -> FastAPI:
    """Everything has a default from the environment; the tests pass fakes (database, queues,
    the other services, a clock they can move forward) and run the background work themselves."""
    settings = settings or Settings.from_env()
    engine = engine or create_engine(settings.database_url, pool_pre_ping=True)
    queues = queues or Queues()
    pricing = pricing or Pricing.from_file(settings.pricing_file)
    sessions = sessionmaker(engine, expire_on_commit=False)
    services = Services(settings.project_service_url, settings.dataset_service_url, transport)
    lifecycle = Lifecycle(clock, settings.heartbeat_timeout_seconds)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        stop = None
        if start_background:
            stop = start_loops(
                sessions,
                queues,
                lifecycle,
                settings.sweep_interval_seconds,
                settings.outbox_interval_seconds,
                settings.dlq_wait_seconds,
                settings.dlq_max_requeues,
            )
        yield
        if stop:
            stop()

    def database_ready() -> bool:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception:
            return False
        return True

    app = FastAPI(title="CloudTrain Training Jobs service", version="1.0.0", lifespan=lifespan)
    logger = setup_service(app, SERVICE_NAME, is_ready=lambda: database_ready() and queues.ready())
    app.state.sessions = sessions
    app.state.lifecycle = lifecycle
    app.state.queues = queues

    def get_session():
        with sessions() as session:
            yield session

    SessionDep = Annotated[Session, Depends(get_session)]

    def send_now() -> None:
        """Send the messages just saved. If SQS is down, the watchdog sends them later."""
        try:
            publish_outbox(sessions, queues, clock)
        except Exception:
            logger.exception("could not send queue messages now; the watchdog will retry")

    def load(session: Session, job_id: str, lock: bool = False) -> Job:
        number = job_number(job_id)
        query = select(Job).where(Job.id == number)
        job = session.scalar(query.with_for_update() if lock else query) if number else None
        if job is None:
            raise ApiError(404, "JOB_NOT_FOUND", f"Job {job_id} does not exist")
        return job

    def job_json(job: Job) -> dict:
        usage = pricing.usage(job, clock())
        return {
            "job_id": job.public_id,
            "project_id": job.project_id,
            "status": job.status,
            "spec": job.spec,
            "machine_type": job.machine_type,
            "attempt": job.attempt,
            "created_at": iso(aware(job.created_at)),
            "updated_at": iso(aware(job.updated_at)),
            "started_at": iso(aware(job.started_at)) if job.started_at else None,
            "finished_at": iso(aware(job.finished_at)) if job.finished_at else None,
            "gpu_hours": usage.gpu_hours,
            "estimated_cost_usd": usage.estimated_cost_usd,
            "history": [
                {"status": e.data["status"], "at": iso(aware(e.occurred_at)), "reason": e.data.get("reason")}
                for e in job.events
            ],
        }

    def event_list(events: list[Event], jobs: dict[int, Job], after: str | None) -> dict:
        items = [event_json(e, jobs[e.job_id]) for e in events]
        return {"items": items, "last_event_id": items[-1]["event_id"] if items else after}

    # ---------- public (through the gateway at /api/v1/jobs/*) ----------

    @app.post("/jobs", status_code=202)
    def submit_job(
        body: JobSubmission,
        request: Request,
        session: SessionDep,
        user_id: UserDep,
        idempotency_key: Annotated[
            str | None, Header(alias="Idempotency-Key", min_length=1, max_length=128)
        ] = None,
    ) -> JSONResponse:
        spec = body.model_dump()
        fingerprint = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()

        def saved_answer() -> JSONResponse | None:
            record = session.get(IdempotencyRecord, (user_id, idempotency_key))
            if record is None:
                return None
            if record.request_fingerprint != fingerprint:
                raise ApiError(
                    409, "IDEMPOTENCY_KEY_REUSED", "This Idempotency-Key was already used for another job"
                )
            return JSONResponse(status_code=202, content=record.response_body)

        if idempotency_key and (answer := saved_answer()):
            return answer

        request_id = request.state.request_id
        services.check_member(body.project_id, user_id, request_id)
        services.check_dataset(body.project_id, body.dataset_id, body.dataset_version, user_id, request_id)

        job = lifecycle.submit(session, body.project_id, user_id, spec)
        content = job_json(job)
        if idempotency_key:
            session.add(
                IdempotencyRecord(
                    user_id=user_id,
                    key=idempotency_key,
                    request_fingerprint=fingerprint,
                    job_id=job.id,
                    response_body=content,
                    created_at=clock(),
                )
            )
        try:
            session.commit()
        except IntegrityError:
            # The same key arrived twice at the same moment and the other request won: answer like it.
            session.rollback()
            if idempotency_key and (answer := saved_answer()):
                return answer
            raise
        JOBS_SUBMITTED.inc()
        send_now()
        logger.info("job accepted", extra={"job_id": job.public_id, "request_id": request_id})
        return JSONResponse(status_code=202, content=content)

    @app.get("/jobs")
    def list_jobs(
        project_id: Annotated[str, Query(pattern=r"^project-[0-9]+$")],
        request: Request,
        session: SessionDep,
        user_id: UserDep,
    ) -> dict:
        services.check_member(project_id, user_id, request.state.request_id)
        jobs = session.scalars(select(Job).where(Job.project_id == project_id).order_by(Job.id)).all()
        return {"items": [job_json(job) for job in jobs]}

    @app.get("/jobs/events")
    def alert_feed(
        request: Request,
        session: SessionDep,
        user_id: UserDep,
        after: Annotated[str | None, Query(pattern=r"^event-[0-9]+$")] = None,
        project_id: Annotated[str | None, Query(pattern=r"^project-[0-9]+$")] = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> dict:
        """Events of the caller's projects only, oldest first. The portal passes the last event_id."""
        if project_id:
            try:
                services.check_member(project_id, user_id, request.state.request_id)
            except ApiError as error:
                if error.status_code != 404:
                    raise
                # The contract has no 404 here: an unknown project is simply not one of yours.
                raise ApiError(403, "NOT_A_MEMBER", f"You are not a member of {project_id}") from None
            projects = [project_id]
        else:
            projects = services.my_projects(user_id, request.state.request_id)
        start = int(after.removeprefix("event-")) if after else 0
        if not projects or start >= MAX_DB_ID:
            return {"items": [], "last_event_id": after}
        events = session.scalars(
            select(Event)
            .where(Event.project_id.in_(projects), Event.id > start)
            .order_by(Event.id)
            .limit(limit)
        ).all()
        numbers = sorted({e.job_id for e in events})
        jobs = {job.id: job for job in session.scalars(select(Job).where(Job.id.in_(numbers)))}
        return event_list(list(events), jobs, after)

    @app.get("/jobs/{job_id}")
    def get_job(job_id: JobIdPath, request: Request, session: SessionDep, user_id: UserDep) -> dict:
        job = load(session, job_id)
        services.check_member(job.project_id, user_id, request.state.request_id)
        return job_json(job)

    @app.post("/jobs/{job_id}/cancel")
    def cancel_job(job_id: JobIdPath, request: Request, session: SessionDep, user_id: UserDep) -> dict:
        project_id = load(session, job_id).project_id
        services.check_member(project_id, user_id, request.state.request_id)  # before taking the lock
        session.rollback()  # end the read, then lock the row
        job = load(session, job_id, lock=True)
        lifecycle.cancel(session, job, user_id)
        session.commit()
        send_now()
        return job_json(job)

    @app.get("/jobs/{job_id}/events")
    def job_events(job_id: JobIdPath, request: Request, session: SessionDep, user_id: UserDep) -> dict:
        job = load(session, job_id)
        services.check_member(job.project_id, user_id, request.state.request_id)
        return event_list(list(job.events), {job.id: job}, None)

    # ---------- internal (Scheduler and worker; the gateway blocks /internal/) ----------

    @app.get("/internal/jobs/{job_id}")
    def internal_job_status(job_id: JobIdPath, session: SessionDep) -> dict:
        """Read-only, for the Scheduler: free a slot when the job ended or its attempt changed (#102)."""
        job = load(session, job_id)
        return {
            "job_id": job.public_id,
            "status": job.status,
            "attempt": job.attempt,
            "machine_type": job.machine_type,
            "updated_at": iso(aware(job.updated_at)),
        }

    @app.post("/internal/jobs/{job_id}/status")
    def report_status(job_id: JobIdPath, report: StatusReport, session: SessionDep) -> dict:
        job = load(session, job_id, lock=True)
        lifecycle.report(session, job, report)
        session.commit()
        send_now()
        return job_json(job)

    @app.post("/internal/jobs/{job_id}/heartbeat")
    def heartbeat(job_id: JobIdPath, beat: Heartbeat, session: SessionDep) -> dict:
        job = load(session, job_id, lock=True)
        status = lifecycle.heartbeat(job, beat)
        session.commit()
        return {"job_id": job.public_id, "status": status}  # CANCELLED tells the worker to stop

    return app
