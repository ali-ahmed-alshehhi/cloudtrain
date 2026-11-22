"""Thin HTTP API for the modular training worker runtime."""

import os

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.common import ApiError, iso, now_utc, setup_service
from app.dataset import DatasetClient
from app.models import TrainingJob
from app.runtime import Worker
from app.tracking import tracker_for
from app.trainer import train_cifar

SERVICE_NAME = "training-worker"


def create_app(
    transport: httpx.BaseTransport | None = None,
    *,
    dataset_client=None,
    trainer=None,
    tracker_factory=None,
    heartbeat_seconds: float | None = None,
    runtime_minute_seconds: float = 60,
) -> FastAPI:
    """Build the service; injectable dependencies keep lifecycle tests fast and deterministic."""
    app = FastAPI(title="CloudTrain Training worker", version="1.0.0")
    logger = setup_service(app, SERVICE_NAME)
    timeout = float(os.environ.get("HTTP_TIMEOUT_SECONDS", "30"))
    http = httpx.Client(transport=transport, timeout=timeout, follow_redirects=True)
    datasets = dataset_client or DatasetClient(
        http,
        os.environ.get("DATASET_SERVICE_URL", "http://dataset-service:8002"),
    )
    worker = Worker(
        http=http,
        logger=logger,
        job_service_url=os.environ.get("JOB_SERVICE_URL", "http://job-service:8003"),
        dataset_client=datasets,
        trainer=trainer or train_cifar,
        tracker_factory=tracker_factory or tracker_for,
        heartbeat_seconds=heartbeat_seconds
        if heartbeat_seconds is not None
        else float(os.environ.get("HEARTBEAT_INTERVAL_SECONDS", "30")),
        runtime_minute_seconds=runtime_minute_seconds,
    )
    app.state.worker = worker

    @app.post("/internal/run", status_code=202)
    def run(job: TrainingJob) -> JSONResponse:
        if not worker.busy.acquire(blocking=False):
            raise ApiError(409, "WORKER_BUSY", "This worker is already running a job")
        worker.start(job)
        return JSONResponse(
            status_code=202,
            content={"job_id": job.job_id, "worker_id": worker.worker_id, "accepted_at": iso(now_utc())},
        )

    return app
