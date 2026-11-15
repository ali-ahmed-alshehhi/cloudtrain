"""Scheduler (owner: Maitha). Reads the training-jobs queue, picks a machine,
checks capacity, hands the job to a worker, and releases the slot when done.

What it does:
- ONLY reader of the `training-jobs` queue (long polling, 20 s wait)
- picks CPU or GPU machine type based on gpu_count (see machines.py)
- enforces a concurrency limit via CapacityTracker (one local worker by default)
- for each job: checks capacity, reports SCHEDULED, hands to the worker, reports RUNNING,
  then deletes the queue message
- a 409 from Training Jobs means the job was cancelled: drop and release
"""

import json
import os
import threading
import time
from contextlib import asynccontextmanager

import boto3
import httpx
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import FastAPI

from app.capacity import CapacityTracker
from app.common import iso, now_utc, setup_service
from app.machines import LOCAL_MACHINE, pick_machine

SERVICE_NAME = "scheduler"
QUEUE_ERRORS = (BotoCoreError, ClientError)
BUSY_RETRY_SECONDS = 5


def sqs_client():
    return boto3.client(
        "sqs",
        endpoint_url=os.environ.get("SQS_ENDPOINT") or None,
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
    )


class Scheduler:
    def __init__(
        self,
        sqs,
        http: httpx.Client,
        logger,
        capacity: CapacityTracker | None = None,
    ) -> None:
        self.sqs = sqs
        self.http = http
        self.logger = logger
        self.queue_name = os.environ.get("TRAINING_JOBS_QUEUE", "training-jobs")
        self.job_service = os.environ.get("JOB_SERVICE_URL", "http://job-service:8003")
        self.worker = os.environ.get("TRAINING_WORKER_URL", "http://training-worker:8010")
        self.max_wait_for_worker = float(os.environ.get("SQS_VISIBILITY_TIMEOUT_SECONDS", "300"))
        self._queue_url: str | None = None
        max_w = int(os.environ.get("SCHEDULER_MAX_WORKERS", "1"))
        self.capacity = capacity or CapacityTracker(max_workers=max_w)

    def queue_url(self) -> str:
        if self._queue_url is None:
            self._queue_url = self.sqs.get_queue_url(QueueName=self.queue_name)["QueueUrl"]
        return self._queue_url

    def ready(self) -> bool:
        try:
            self.queue_url()
        except QUEUE_ERRORS:
            return False
        return True

    def report(
        self,
        job_id: str,
        status: str,
        machine_type: str = LOCAL_MACHINE,
        **details,
    ) -> httpx.Response:
        body = {"status": status, "reported_by": "scheduler", "machine_type": machine_type, **details}
        return self.http.post(f"{self.job_service}/internal/jobs/{job_id}/status", json=body)

    def handle_job(self, form: dict) -> bool:
        """Place one job. Returns True when the queue message can be deleted."""
        job_id = form["job_id"]
        gpu_count = form.get("resources", {}).get("gpu_count", 0)
        machine = pick_machine(gpu_count)

        # Check capacity before doing anything
        if not self.capacity.reserve(job_id, machine):
            self.logger.info(
                "no capacity; message stays on queue",
                extra={"job_id": job_id, "active": self.capacity.active_count},
            )
            return False

        scheduled = self.report(job_id, "SCHEDULED", machine_type=machine)
        if scheduled.status_code == 409:
            self.capacity.release(job_id)
            self.logger.info("job cancelled or already scheduled; dropping message", extra={"job_id": job_id})
            return True
        if scheduled.status_code != 200:
            self.capacity.release(job_id)
            return False

        waited = 0.0
        while True:
            answer = self.http.post(f"{self.worker}/internal/run", json=form)
            if answer.status_code == 202:
                break
            if answer.status_code != 409 or waited >= self.max_wait_for_worker:
                self.capacity.release(job_id)
                self.logger.error("worker did not accept the job", extra={"job_id": job_id})
                return False
            time.sleep(BUSY_RETRY_SECONDS)
            waited += BUSY_RETRY_SECONDS

        running = self.report(job_id, "RUNNING", machine_type=machine, started_at=iso(now_utc()))
        if running.status_code == 409:
            self.capacity.release(job_id)
            self.logger.info("job was cancelled while starting", extra={"job_id": job_id})
        return True

    def release_job(self, job_id: str) -> None:
        """Called when a job finishes or fails — free the capacity slot."""
        released = self.capacity.release(job_id)
        if released:
            self.logger.info("released machine", extra={"job_id": job_id, "machine": released})

    def read_queue_once(self) -> None:
        answer = self.sqs.receive_message(
            QueueUrl=self.queue_url(), MaxNumberOfMessages=1, WaitTimeSeconds=20
        )
        for message in answer.get("Messages", []):
            try:
                done = self.handle_job(json.loads(message["Body"]))
            except httpx.HTTPError:
                self.logger.exception("could not reach the job service or the worker")
                done = False
            if done:
                self.sqs.delete_message(QueueUrl=self.queue_url(), ReceiptHandle=message["ReceiptHandle"])


def create_app(
    sqs=None,
    transport: httpx.BaseTransport | None = None,
    start_loop: bool = True,
    capacity: CapacityTracker | None = None,
) -> FastAPI:
    """`sqs`, `transport` and `capacity` let the tests inject fakes."""
    holder: dict[str, Scheduler] = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        stop = threading.Event()

        def loop() -> None:
            while not stop.is_set():
                try:
                    scheduler.read_queue_once()
                except QUEUE_ERRORS:
                    logger.exception("queue not reachable; trying again in 5 seconds")
                    stop.wait(5)

        if start_loop:
            threading.Thread(target=loop, daemon=True, name="queue-reader").start()
        yield
        stop.set()

    app = FastAPI(title="CloudTrain Scheduler", version="1.0.0", lifespan=lifespan)
    logger = setup_service(app, SERVICE_NAME, is_ready=lambda: holder["scheduler"].ready())
    scheduler = Scheduler(
        sqs or sqs_client(),
        httpx.Client(transport=transport, timeout=10),
        logger,
        capacity=capacity,
    )
    holder["scheduler"] = scheduler
    app.state.scheduler = scheduler
    return app
