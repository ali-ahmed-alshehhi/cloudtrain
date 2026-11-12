"""STAND-IN for the Scheduler (owner: Maitha). Replace it with the real service; keep the contract.

What this stand-in already does:
- it is the ONLY reader of the `training-jobs` queue (long polling: it waits up to 20 seconds for a
  message instead of asking again and again)
- for each job: reports SCHEDULED to the Training Jobs service, hands the job to the one local worker
  (POST /internal/run, waiting while the worker is busy), reports RUNNING, then deletes the message
- a 409 from Training Jobs means the job was cancelled or already handled: the message is dropped
What it does NOT do (the real scheduler must): choose CPU or GPU machines, start cloud workers,
capacity, quotas, release machines, use its PostgreSQL schema.
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

from app.common import iso, now_utc, setup_service

SERVICE_NAME = "scheduler"
QUEUE_ERRORS = (BotoCoreError, ClientError)
LOCAL_MACHINE = "local-cpu"  # the only machine type a laptop has (see contracts/pricing.yaml)
BUSY_RETRY_SECONDS = 5


def sqs_client():
    return boto3.client(
        "sqs",
        endpoint_url=os.environ.get("SQS_ENDPOINT") or None,
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
    )


class Scheduler:
    def __init__(self, sqs, http: httpx.Client, logger) -> None:
        self.sqs = sqs
        self.http = http
        self.logger = logger
        self.queue_name = os.environ.get("TRAINING_JOBS_QUEUE", "training-jobs")
        self.job_service = os.environ.get("JOB_SERVICE_URL", "http://job-service:8003")
        self.worker = os.environ.get("TRAINING_WORKER_URL", "http://training-worker:8010")
        self.max_wait_for_worker = float(os.environ.get("SQS_VISIBILITY_TIMEOUT_SECONDS", "300"))
        self._queue_url: str | None = None

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

    def report(self, job_id: str, status: str, **details) -> httpx.Response:
        body = {"status": status, "reported_by": "scheduler", "machine_type": LOCAL_MACHINE, **details}
        return self.http.post(f"{self.job_service}/internal/jobs/{job_id}/status", json=body)

    def handle_job(self, form: dict) -> bool:
        """Place one job. Returns True when the queue message can be deleted."""
        job_id = form["job_id"]
        scheduled = self.report(job_id, "SCHEDULED")
        if scheduled.status_code == 409:
            self.logger.info("job cancelled or already scheduled; dropping message", extra={"job_id": job_id})
            return True
        if scheduled.status_code != 200:
            return False  # Training Jobs is unhappy; the message comes back later

        waited = 0.0
        while True:  # wait while the single local worker is busy ("queueing when capacity is full")
            answer = self.http.post(f"{self.worker}/internal/run", json=form)
            if answer.status_code == 202:
                break
            if answer.status_code != 409 or waited >= self.max_wait_for_worker:
                self.logger.error("worker did not accept the job", extra={"job_id": job_id})
                return False
            time.sleep(BUSY_RETRY_SECONDS)
            waited += BUSY_RETRY_SECONDS

        running = self.report(job_id, "RUNNING", started_at=iso(now_utc()))
        if running.status_code == 409:
            self.logger.info("job was cancelled while starting", extra={"job_id": job_id})
        return True

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


def create_app(sqs=None, transport: httpx.BaseTransport | None = None, start_loop: bool = True) -> FastAPI:
    """`sqs` and `transport` let the tests replace SQS and the other services with fakes."""
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

    app = FastAPI(title="CloudTrain Scheduler (stand-in)", version="1.0.0", lifespan=lifespan)
    logger = setup_service(app, SERVICE_NAME, is_ready=lambda: holder["scheduler"].ready())
    scheduler = Scheduler(sqs or sqs_client(), httpx.Client(transport=transport, timeout=10), logger)
    holder["scheduler"] = scheduler
    app.state.scheduler = scheduler
    return app
