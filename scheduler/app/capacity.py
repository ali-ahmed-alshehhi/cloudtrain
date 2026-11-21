"""Track busy workers and enforce concurrency limits."""

import threading

from app.machines import CLOUD_MACHINES

# Default: 1 local worker, configurable via environment in main.py
DEFAULT_MAX_WORKERS = 1


class CapacityTracker:
    """Thread-safe tracker for machines currently running jobs."""

    def __init__(self, max_workers: int = DEFAULT_MAX_WORKERS, max_gpus: int | None = None) -> None:
        self._lock = threading.Lock()
        self._max_workers = max_workers
        self._max_gpus = max_gpus  # None means no GPU limit
        # job_id -> machine_type
        self._active: dict[str, str] = {}

    @property
    def max_workers(self) -> int:
        return self._max_workers

    @property
    def max_gpus(self) -> int | None:
        return self._max_gpus

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._active)

    @property
    def active_jobs(self) -> dict[str, str]:
        """Return a snapshot of {job_id: machine_type}."""
        with self._lock:
            return dict(self._active)

    def has_capacity(self) -> bool:
        """True when at least one more job can be placed."""
        with self._lock:
            return len(self._active) < self._max_workers

    def _gpus_for(self, machine_type: str) -> int:
        """GPUs provided by this machine type (from pricing contract)."""
        gpu_map = {v: k for k, v in CLOUD_MACHINES.items()}
        return gpu_map.get(machine_type, 0)

    def reserve(self, job_id: str, machine_type: str) -> bool:
        """Reserve a slot for this job. Returns False if full, GPU quota exceeded, or already tracked."""
        with self._lock:
            if len(self._active) >= self._max_workers:
                return False
            if job_id in self._active:
                return False
            # GPU quota check (when set)
            if self._max_gpus is not None:
                needed = self._gpus_for(machine_type)
                current = sum(self._gpus_for(m) for m in self._active.values())
                if current + needed > self._max_gpus:
                    return False
            self._active[job_id] = machine_type
            return True

    def release(self, job_id: str) -> str | None:
        """Release the slot for this job. Returns the machine type, or None if not found."""
        with self._lock:
            return self._active.pop(job_id, None)

    def gpu_in_use(self) -> int:
        """Total GPUs currently reserved across all active jobs."""
        with self._lock:
            return sum(self._gpus_for(m) for m in self._active.values())
