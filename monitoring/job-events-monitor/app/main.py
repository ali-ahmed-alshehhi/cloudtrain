"""job-events-monitor (owners: Hilal + Adel, Student 10).

The only reader of the job-events queue. It turns job events into metrics:
GET /metrics for Prometheus (local dashboard), and CloudWatch EMF log lines (AWS).
It has no API of its own besides GET /health and GET /metrics. Port 8011 (proposal #109).

Run: uvicorn --factory app.main:create_app --port 8011
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.common import setup_service
from app.consumer import Consumer
from app.metrics import Metrics
from app.queue import JobEventsQueue
from app.settings import Settings
from app.tracker import Tracker

SERVICE_NAME = "job-events-monitor"
_METRICS: Metrics | None = None  # Prometheus refuses the same metric name twice in one process


def shared_metrics() -> Metrics:
    global _METRICS
    if _METRICS is None:
        _METRICS = Metrics()
    return _METRICS


def create_app(
    settings: Settings | None = None,
    queue: JobEventsQueue | None = None,
    metrics: Metrics | None = None,
    start_consumer: bool = True,
) -> FastAPI:
    settings = settings or Settings()
    metrics = metrics or shared_metrics()
    queue = queue or JobEventsQueue(settings.queue_name, settings.sqs_endpoint, settings.aws_region)
    tracker = Tracker.from_file(settings.schema_path)
    holder: dict = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if start_consumer:
            holder["consumer"].start()
        yield
        holder["consumer"].stop(timeout=settings.wait_seconds + 5)

    app = FastAPI(title=SERVICE_NAME, lifespan=lifespan)
    logger = setup_service(
        app,
        SERVICE_NAME,
        is_ready=lambda: holder["consumer"].is_healthy(settings.healthy_within_seconds),
    )
    consumer = Consumer(
        queue, tracker, metrics, logger, wait_seconds=settings.wait_seconds, emf=settings.emf_enabled
    )
    holder["consumer"] = consumer
    app.state.consumer = consumer
    return app
