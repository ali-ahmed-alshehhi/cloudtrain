"""GPU-hours and estimated cost of a job, from contracts/pricing.yaml.

    hours of an attempt   = finished_at - started_at   (still running: now - started_at)
    gpu_hours of a job    = resources.gpu_count x hours, summed over every attempt
    estimated_cost_usd    = hourly price of the machine x hours, summed over every attempt

Why every attempt: a run that failed still kept its machine busy, and AWS bills that time.
Why the job's gpu_count for gpu_hours but the machine's price for cost: gpu_hours says how much GPU
the training used (what part 5 compares), cost says what we pay for the whole machine.
A machine type missing from pricing.yaml makes the cost null ("price unknown", #108), never 0:
0 means free (local-cpu). gpu_hours stay exact. The missing type is logged; the job is not affected.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

from app.db import Job, aware

logger = logging.getLogger("job-service")


@dataclass(frozen=True)
class Usage:
    gpu_hours: float
    estimated_cost_usd: float | None  # None: a machine that ran has no price in pricing.yaml


class Pricing:
    def __init__(self, hourly_usd: dict[str, float]) -> None:
        self.hourly_usd = hourly_usd

    @classmethod
    def from_file(cls, path: str | Path) -> "Pricing":
        if not Path(path).is_file():
            raise FileNotFoundError(
                f"PRICING_FILE {path} does not exist. The image copies contracts/pricing.yaml to "
                "/contracts/pricing.yaml; build it with Compose, or with --build-context contracts=contracts"
            )
        data = yaml.safe_load(Path(path).read_text()) or {}
        machines = data.get("machine_types") or {}
        return cls({name: float(info.get("hourly_usd") or 0) for name, info in machines.items()})

    def hourly(self, machine_type: str | None) -> float | None:
        """The price per hour, or None when unknown (no machine reported, or not in pricing.yaml)."""
        if machine_type not in self.hourly_usd:
            logger.warning("machine type %s is not in pricing.yaml; cost is unknown", machine_type)
            return None
        return self.hourly_usd[machine_type]

    def usage(self, job: Job, now: datetime) -> Usage:
        gpu_count = int(job.spec.get("resources", {}).get("gpu_count", 0))
        gpu_hours = cost = 0.0
        price_known = True
        for attempt in job.attempts:
            started = aware(attempt.started_at)
            if started is None:
                continue  # never started running: no machine time
            finished = aware(attempt.finished_at) or now
            hours = max((finished - started).total_seconds(), 0) / 3600
            gpu_hours += gpu_count * hours
            hourly = self.hourly(attempt.machine_type)
            if hourly is None:
                price_known = False  # one unknown price makes the total unknown
            else:
                cost += hourly * hours
        return Usage(
            gpu_hours=round(gpu_hours, 4),
            estimated_cost_usd=round(cost, 4) if price_known else None,
        )
