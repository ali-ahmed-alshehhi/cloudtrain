"""STAND-IN for the Training Jobs service (owner: Mariam). Replace it; keep the contract.

What this stand-in already does, as contracts/openapi/job-service.yaml and contracts/job-states.md say:
- POST /jobs checks the form, asks the Datasets service if the version exists, answers 202 and puts
  the full form on the `training-jobs` queue
- follows the status steps reported by the Scheduler and the worker; anything else gets 409
- stores every change as an event (served by the alert feed) and sends it to the `job-events` queue
- cancel, and the heartbeat answer (which tells a worker its job's status)
What it does NOT do — Mariam's real service must:
- use PostgreSQL (everything here is lost on restart) and check project membership
- detect a dead worker (no heartbeat for HEARTBEAT_TIMEOUT_SECONDS) and the max_runtime_minutes limit,
  so a job can never stay RUNNING forever
- retry FAILED jobs while retry_limit allows (event job.retrying), then report to training-jobs-dlq
- compute gpu_hours and estimated_cost_usd from contracts/pricing.yaml (always 0 here)
"""

import os
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi import Path as PathParam
from fastapi.responses import JSONResponse

from app.common import ApiError, current_user, iso, now_utc, setup_service
from app.models import Heartbeat, JobSubmission, StatusReport
from app.queues import QUEUE_ERRORS, Queues

SERVICE_NAME = "job-service"
JobIdPath = Annotated[str, PathParam(pattern=r"^job-[0-9]+$")]
UserDep = Annotated[str, Depends(current_user)]

# Which status may follow which (contracts/job-states.md). CANCELLED is handled by POST /jobs/{id}/cancel.
ALLOWED_STEPS = {
    "QUEUED": {"SCHEDULED"},
    "SCHEDULED": {"RUNNING"},
    "RUNNING": {"SUCCEEDED", "FAILED"},
}
CANCELLABLE = {"QUEUED", "SCHEDULED", "RUNNING"}


@dataclass
class Job:
    number: int
    spec: dict
    status: str = "QUEUED"
    machine_type: str | None = None
    attempt: int = 1
    created_at: datetime = field(default_factory=now_utc)
    updated_at: datetime = field(default_factory=now_utc)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    history: list[dict] = field(default_factory=list)

    @property
    def job_id(self) -> str:
        return f"job-{self.number:02d}"

    def form(self) -> dict:
        """The full training job form that goes on the queue (contracts/training-job.schema.json)."""
        return {"job_id": self.job_id, **self.spec}


def job_json(job: Job) -> dict:
    return {
        "job_id": job.job_id,
        "project_id": job.spec["project_id"],
        "status": job.status,
        "spec": job.spec,
        "machine_type": job.machine_type,
        "attempt": job.attempt,
        "created_at": iso(job.created_at),
        "updated_at": iso(job.updated_at),
        "started_at": iso(job.started_at) if job.started_at else None,
        "finished_at": iso(job.finished_at) if job.finished_at else None,
        "gpu_hours": 0.0,  # STAND-IN: Mariam computes these from the machine type and contracts/pricing.yaml
        "estimated_cost_usd": 0.0,
        "history": job.history,
    }


def create_app(
    queues: Queues | None = None,
    transport: httpx.BaseTransport | None = None,
) -> FastAPI:
    """`queues` and `transport` let the tests replace SQS and the Datasets service with fakes."""
    queues = queues or Queues()
    datasets = httpx.Client(
        base_url=os.environ.get("DATASET_SERVICE_URL", "http://dataset-service:8002"),
        transport=transport,
        timeout=10,
    )
    app = FastAPI(title="CloudTrain Training Jobs service (stand-in)", version="1.0.0")
    logger = setup_service(app, SERVICE_NAME, is_ready=queues.ready)

    jobs: dict[int, Job] = {}
    events: list[dict] = []
    saved_answers: dict[tuple[str, str], dict] = {}
    lock = threading.Lock()  # several requests may change the same job at once

    def find(job_id: str) -> Job:
        job = jobs.get(int(job_id.removeprefix("job-")))
        if job is None:
            raise ApiError(404, "JOB_NOT_FOUND", f"Job {job_id} does not exist")
        return job

    def record_event(job: Job, event_type: str, previous: str | None, reason: str | None) -> None:
        event = {
            "event_id": f"event-{len(events) + 1}",
            "event_type": event_type,
            "job_id": job.job_id,
            "project_id": job.spec["project_id"],
            "occurred_at": iso(now_utc()),
            "data": {
                "status": job.status,
                "previous_status": previous,
                "reason": reason,
                "machine_type": job.machine_type,
                "attempt": job.attempt,
            },
        }
        events.append(event)
        try:
            queues.send("job-events", event)
        except QUEUE_ERRORS:
            logger.exception("could not publish event", extra={"job_id": job.job_id})

    def change_status(job: Job, new_status: str, reason: str | None = None) -> None:
        previous = job.status
        job.status = new_status
        job.updated_at = now_utc()
        job.history.append({"status": new_status, "at": iso(job.updated_at), "reason": reason})
        record_event(job, f"job.{new_status.lower()}", previous, reason)

    # ---------- public ----------

    @app.post("/jobs", status_code=202)
    def submit_job(
        body: JobSubmission,
        request: Request,
        user_id: UserDep,
        idempotency_key: Annotated[
            str | None, Header(alias="Idempotency-Key", min_length=1, max_length=128)
        ] = None,
    ) -> JSONResponse:
        if idempotency_key and (user_id, idempotency_key) in saved_answers:
            return JSONResponse(status_code=202, content=saved_answers[(user_id, idempotency_key)])

        # Internal call: does this dataset version exist? (never through the gateway)
        try:
            answer = datasets.get(
                f"/datasets/{body.dataset_id}/versions/{body.dataset_version}",
                headers={"X-User-Id": user_id, "X-Request-Id": request.state.request_id},
            )
        except httpx.HTTPError:
            raise ApiError(503, "SERVICE_UNAVAILABLE", "The Datasets service is not reachable") from None
        if answer.status_code == 404:
            raise ApiError(
                404,
                "DATASET_VERSION_NOT_FOUND",
                f"Dataset {body.dataset_id} version {body.dataset_version} does not exist",
            )
        if answer.status_code == 403:
            raise ApiError(403, "NOT_A_MEMBER", f"You are not a member of {body.project_id}")
        if answer.status_code != 200:
            raise ApiError(503, "SERVICE_UNAVAILABLE", "The Datasets service could not confirm the version")

        with lock:
            job = Job(number=len(jobs) + 1, spec=body.model_dump())
            try:
                queues.send("training-jobs", job.form())
            except QUEUE_ERRORS:
                raise ApiError(
                    503, "SERVICE_UNAVAILABLE", "The training-jobs queue is not reachable"
                ) from None
            jobs[job.number] = job
            job.history.append({"status": "QUEUED", "at": iso(job.created_at), "reason": None})
            record_event(job, "job.queued", None, None)
            content = job_json(job)
        if idempotency_key:
            saved_answers[(user_id, idempotency_key)] = content
        return JSONResponse(status_code=202, content=content)

    @app.get("/jobs")
    def list_jobs(project_id: Annotated[str, Query(pattern=r"^project-[0-9]+$")], user_id: UserDep) -> dict:
        return {"items": [job_json(job) for job in jobs.values() if job.spec["project_id"] == project_id]}

    @app.get("/jobs/events")
    def alert_feed(
        user_id: UserDep,
        after: Annotated[str | None, Query(pattern=r"^event-[0-9]+$")] = None,
        project_id: Annotated[str | None, Query(pattern=r"^project-[0-9]+$")] = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> dict:
        # STAND-IN: shows events of every project (the real service shows only the caller's projects).
        start = int(after.removeprefix("event-")) if after else 0
        found = [e for e in events[start:] if project_id in (None, e["project_id"])][:limit]
        return {"items": found, "last_event_id": found[-1]["event_id"] if found else after}

    @app.get("/jobs/{job_id}")
    def get_job(job_id: JobIdPath, user_id: UserDep) -> dict:
        return job_json(find(job_id))

    @app.post("/jobs/{job_id}/cancel")
    def cancel_job(job_id: JobIdPath, user_id: UserDep) -> dict:
        with lock:
            job = find(job_id)
            if job.status not in CANCELLABLE:
                raise ApiError(
                    409, "JOB_ALREADY_FINISHED", f"Job {job_id} is {job.status} and cannot be cancelled"
                )
            change_status(job, "CANCELLED", f"cancelled by {user_id}")
            return job_json(job)

    @app.get("/jobs/{job_id}/events")
    def job_events(job_id: JobIdPath, user_id: UserDep) -> dict:
        found = [e for e in events if e["job_id"] == find(job_id).job_id]
        return {"items": found, "last_event_id": found[-1]["event_id"] if found else None}

    # ---------- internal (Scheduler and worker; never through the gateway) ----------

    @app.post("/internal/jobs/{job_id}/status")
    def report_status(job_id: JobIdPath, report: StatusReport) -> dict:
        with lock:
            job = find(job_id)
            if report.status not in ALLOWED_STEPS.get(job.status, set()):
                raise ApiError(
                    409,
                    "INVALID_STATUS_TRANSITION",
                    f"Job {job_id} is {job.status}; it cannot become {report.status}",
                )
            if report.machine_type:
                job.machine_type = report.machine_type
            if report.status == "RUNNING":
                job.started_at = report.started_at or now_utc()
            if report.status in ("SUCCEEDED", "FAILED"):
                job.finished_at = report.finished_at or now_utc()
            change_status(job, report.status, report.reason)
            return job_json(job)

    @app.post("/internal/jobs/{job_id}/heartbeat")
    def heartbeat(job_id: JobIdPath, beat: Heartbeat) -> dict:
        # STAND-IN: the beat is not recorded (Mariam's service uses it to detect a dead worker).
        job = find(job_id)
        return {"job_id": job.job_id, "status": job.status}  # CANCELLED tells the worker to stop

    return app
