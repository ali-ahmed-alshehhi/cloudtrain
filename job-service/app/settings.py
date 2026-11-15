"""Every setting of the Training Jobs service, read once from environment variables (.env locally).

Nothing is hard-coded: each value below has the same name in .env.example.
"""

import os
from dataclasses import dataclass


def _number(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


@dataclass(frozen=True)
class Settings:
    database_url: str = ""
    dataset_service_url: str = "http://dataset-service:8002"
    project_service_url: str = "http://project-service:8001"
    pricing_file: str = "/contracts/pricing.yaml"
    # Worker heartbeat (contracts/job-states.md: settings, not contract rules; timeout >= 3 x interval)
    heartbeat_interval_seconds: float = 30
    heartbeat_timeout_seconds: float = 120
    # How often the watchdog looks for silent workers and jobs past their time limit
    sweep_interval_seconds: float = 10
    # How often unsent queue messages (the outbox) are retried
    outbox_interval_seconds: float = 2
    # How long to wait for a message on the dead-letter queue (SQS long polling)
    dlq_wait_seconds: int = 20
    # A job whose queue message reached the dead-letter queue is put back this many times at most
    dlq_max_requeues: int = 3

    @classmethod
    def from_env(cls) -> "Settings":
        settings = cls(
            database_url=os.environ.get("DATABASE_URL", ""),
            dataset_service_url=os.environ.get("DATASET_SERVICE_URL", cls.dataset_service_url),
            project_service_url=os.environ.get("PROJECT_SERVICE_URL", cls.project_service_url),
            pricing_file=os.environ.get("PRICING_FILE", cls.pricing_file),
            heartbeat_interval_seconds=_number("HEARTBEAT_INTERVAL_SECONDS", 30),
            heartbeat_timeout_seconds=_number("HEARTBEAT_TIMEOUT_SECONDS", 120),
            sweep_interval_seconds=_number("JOB_SWEEP_INTERVAL_SECONDS", 10),
            outbox_interval_seconds=_number("JOB_OUTBOX_INTERVAL_SECONDS", 2),
            dlq_wait_seconds=int(_number("JOB_DLQ_WAIT_SECONDS", 20)),
            dlq_max_requeues=int(_number("JOB_DLQ_MAX_REQUEUES", 3)),
        )
        settings.check()
        return settings

    def check(self) -> None:
        """Refuse to start with settings that would break the heartbeat rule."""
        if self.heartbeat_timeout_seconds < 3 * self.heartbeat_interval_seconds:
            raise ValueError(
                "HEARTBEAT_TIMEOUT_SECONDS must be at least 3 x HEARTBEAT_INTERVAL_SECONDS "
                f"(now {self.heartbeat_timeout_seconds} and {self.heartbeat_interval_seconds})"
            )
