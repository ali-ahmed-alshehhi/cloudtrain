"""STAND-IN for the training worker (owner: Abdullah; DDP: Ahmed + Abdulla). Replace it; keep the contract.

What this stand-in already does, as contracts/openapi/training-worker.yaml says:
- POST /internal/run accepts ONE job at a time (202), or 409 WORKER_BUSY
- "trains" by waiting STANDIN_TRAINING_SECONDS (default 3), sending a heartbeat to the Training Jobs
  service every HEARTBEAT_INTERVAL_SECONDS; stops at once if the heartbeat answer says CANCELLED
- reports SUCCEEDED at the end
What it does NOT do (the real worker must): download the dataset, train a model, use GPUs or DDP,
log to MLflow, save checkpoints and the model to S3, report FAILED when training crashes.
"""

import os
import socket
import threading
import time

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.common import ApiError, iso, now_utc, setup_service
from app.models import TrainingJob

SERVICE_NAME = "training-worker"


class Worker:
    def __init__(self, http: httpx.Client, logger) -> None:
        self.http = http
        self.logger = logger
        self.worker_id = f"worker-{socket.gethostname()}"
        self.job_service = os.environ.get("JOB_SERVICE_URL", "http://job-service:8003")
        self.heartbeat_seconds = float(os.environ.get("HEARTBEAT_INTERVAL_SECONDS", "30"))
        self.training_seconds = float(os.environ.get("STANDIN_TRAINING_SECONDS", "3"))
        self.busy = threading.Lock()

    def heartbeat(self, job_id: str) -> str | None:
        """Send "I am still alive"; returns the job's status from the answer."""
        try:
            answer = self.http.post(
                f"{self.job_service}/internal/jobs/{job_id}/heartbeat",
                json={"worker_id": self.worker_id, "sent_at": iso(now_utc())},
            )
            return answer.json().get("status") if answer.status_code == 200 else None
        except httpx.HTTPError:
            self.logger.exception("heartbeat failed", extra={"job_id": job_id})
            return None

    def train(self, job_id: str) -> None:
        """Pretend to train: wait, with heartbeats, then report success."""
        try:
            finish_at = time.monotonic() + self.training_seconds
            while (left := finish_at - time.monotonic()) > 0:
                if self.heartbeat(job_id) == "CANCELLED":
                    self.logger.info("job cancelled; stopping", extra={"job_id": job_id})
                    return
                time.sleep(min(self.heartbeat_seconds, left))
            report = {
                "status": "SUCCEEDED",
                "reported_by": "worker",
                "worker_id": self.worker_id,
                "finished_at": iso(now_utc()),
            }
            self.http.post(f"{self.job_service}/internal/jobs/{job_id}/status", json=report)
            self.logger.info("job finished", extra={"job_id": job_id})
        except httpx.HTTPError:
            self.logger.exception("could not report the result", extra={"job_id": job_id})
        finally:
            self.busy.release()


def create_app(transport: httpx.BaseTransport | None = None) -> FastAPI:
    """`transport` lets the tests replace the Training Jobs service with a fake."""
    app = FastAPI(title="CloudTrain Training worker (stand-in)", version="1.0.0")
    logger = setup_service(app, SERVICE_NAME)
    worker = Worker(httpx.Client(transport=transport, timeout=10), logger)
    app.state.worker = worker

    @app.post("/internal/run", status_code=202)
    def run(job: TrainingJob) -> JSONResponse:
        if not worker.busy.acquire(blocking=False):
            raise ApiError(409, "WORKER_BUSY", "This worker is already running a job")
        threading.Thread(target=worker.train, args=(job.job_id,), daemon=True).start()
        return JSONResponse(
            status_code=202,
            content={"job_id": job.job_id, "worker_id": worker.worker_id, "accepted_at": iso(now_utc())},
        )

    return app
