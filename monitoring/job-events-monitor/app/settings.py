"""Settings, all from environment variables (see .env.example). Nothing secret lives here."""

import os
from dataclasses import dataclass, field
from pathlib import Path

# Inside the image the schema is copied to /contracts (see Dockerfile); in the repo it is ../../contracts.
_IMAGE_SCHEMA = Path("/contracts/events/job-event.schema.json")


def _repo_schema(here: Path) -> Path | None:
    """contracts/ at the repo root, four folders above this file; None when there is no such folder.

    Inside the image this file is /service/app/settings.py, only three folders deep, so asking for
    parents[3] at import time crashed the container (exit 1) before it could start.
    """
    parents = here.resolve().parents
    return parents[3] / "contracts" / "events" / "job-event.schema.json" if len(parents) > 3 else None


def _default_schema(here: Path = Path(__file__)) -> str:
    if _IMAGE_SCHEMA.exists():
        return str(_IMAGE_SCHEMA)
    repo = _repo_schema(here)
    return str(repo if repo is not None else _IMAGE_SCHEMA)


def _flag(name: str, default: str) -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    queue_name: str = field(default_factory=lambda: os.environ.get("JOB_EVENTS_QUEUE", "job-events"))
    sqs_endpoint: str | None = field(default_factory=lambda: os.environ.get("SQS_ENDPOINT") or None)
    aws_region: str = field(default_factory=lambda: os.environ.get("AWS_REGION", "us-east-1"))
    # Long polling: SQS waits up to this long for a message (20 is the SQS maximum).
    wait_seconds: int = field(default_factory=lambda: int(os.environ.get("JOB_EVENTS_WAIT_SECONDS", "20")))
    schema_path: str = field(default_factory=lambda: os.environ.get("JOB_EVENT_SCHEMA", _default_schema()))
    # CloudWatch Embedded Metric Format lines on stdout (turn into CloudWatch metrics on AWS).
    emf_enabled: bool = field(default_factory=lambda: _flag("JOB_EVENTS_EMF", "true"))
    # /health answers 503 when the last successful poll is older than this.
    healthy_within_seconds: int = field(
        default_factory=lambda: int(os.environ.get("JOB_EVENTS_HEALTHY_WITHIN_SECONDS", "120"))
    )
