"""Single-job orchestration with independent heartbeat and timeout supervision."""

import socket
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from pathlib import Path
from typing import Protocol

import httpx

from app.common import iso, now_utc
from app.models import TrainingJob


class DatasetDependency(Protocol):
    def download(self, dataset_id: str, version: int) -> Path: ...


class Worker:
    def __init__(
        self,
        http: httpx.Client,
        logger,
        job_service_url: str,
        dataset_client: DatasetDependency,
        trainer,
        tracker_factory,
        heartbeat_seconds: float,
        runtime_minute_seconds: float = 60,
    ) -> None:
        self.http = http
        self.logger = logger
        self.worker_id = f"worker-{socket.gethostname()}"
        self.job_service = job_service_url.rstrip("/")
        self.dataset_client = dataset_client
        self.trainer = trainer
        self.tracker_factory = tracker_factory
        self.heartbeat_seconds = heartbeat_seconds
        self.runtime_minute_seconds = runtime_minute_seconds
        self.busy = threading.Lock()

    def start(self, job: TrainingJob) -> None:
        threading.Thread(target=self._supervise, args=(job,), daemon=True).start()

    def _supervise(self, job: TrainingJob) -> None:
        stop_event = threading.Event()
        deadline = time.monotonic() + (job.execution.max_runtime_minutes * self.runtime_minute_seconds)
        try:
            with ThreadPoolExecutor(max_workers=1, thread_name_prefix="trainer") as executor:
                future = executor.submit(self._execute, job, stop_event)
                outcome = self._wait(job, future, stop_event, deadline)
            if outcome == "cancelled":
                self.logger.info("job cancelled; no terminal status sent", extra={"job_id": job.job_id})
            elif outcome == "timed_out":
                self._report(
                    job.job_id,
                    "FAILED",
                    f"maximum runtime of {job.execution.max_runtime_minutes} minute(s) exceeded",
                )
            else:
                error = future.exception()
                if error is None:
                    self._report(job.job_id, "SUCCEEDED")
                else:
                    self.logger.error(
                        "training failed",
                        exc_info=(type(error), error, error.__traceback__),
                        extra={"job_id": job.job_id},
                    )
                    self._report(job.job_id, "FAILED", str(error))
        finally:
            self.busy.release()

    def _wait(
        self,
        job: TrainingJob,
        future: Future,
        stop_event: threading.Event,
        deadline: float,
    ) -> str:
        while True:
            if self.heartbeat(job.job_id) == "CANCELLED":
                stop_event.set()
                self._settle(future)
                return "cancelled"
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                stop_event.set()
                self._settle(future)
                return "timed_out"
            try:
                future.result(timeout=min(self.heartbeat_seconds, remaining))
                return "finished"
            except TimeoutError:
                continue
            except Exception:
                return "finished"

    @staticmethod
    def _settle(future: Future) -> None:
        try:
            future.result()
        except Exception:
            pass

    def _execute(self, job: TrainingJob, stop_event: threading.Event) -> dict[str, float]:
        dataset_dir = self.dataset_client.download(job.dataset_id, job.dataset_version)
        record_lineage = getattr(self.dataset_client, "record_lineage", None)
        if record_lineage:
            try:
                record_lineage(job.dataset_id, job.dataset_version, job.job_id)
            except Exception as error:
                self.logger.warning(
                    "dataset lineage record failed",
                    extra={"job_id": job.job_id, "error": str(error)},
                )
        try:
            with self.tracker_factory(job) as tracker:
                from app.trainer import _dataset_checksum

                tracker.log_params(
                    {
                        "model": job.model,
                        "dataset_id": job.dataset_id,
                        "dataset_version": job.dataset_version,
                        "strategy": job.parallelism.strategy,
                        "world_size": job.parallelism.world_size,
                        **job.hyperparameters.model_dump(),
                    }
                )
                if hasattr(tracker, "log_tags"):
                    tracker.log_tags({"dataset_checksum": _dataset_checksum(dataset_dir)})

                def record(epoch: int, metrics: dict[str, float]) -> None:
                    tracker.log_metrics(metrics, step=epoch)

                result = self.trainer(job, dataset_dir, record, stop_event)
                final_metrics = getattr(result, "metrics", result)
                tracker.log_metrics({f"final_{name}": value for name, value in final_metrics.items()})
                if hasattr(result, "model") and hasattr(tracker, "log_model"):
                    tracker.log_model(result.model, result.input_example)
                if getattr(result, "artifact_uri", None) and hasattr(tracker, "log_tags"):
                    tracker.log_tags({"final_model_artifact": result.artifact_uri})
                return final_metrics
        finally:
            cleanup = getattr(self.dataset_client, "cleanup", None)
            if cleanup:
                cleanup(dataset_dir)

    def heartbeat(self, job_id: str) -> str | None:
        try:
            answer = self.http.post(
                f"{self.job_service}/internal/jobs/{job_id}/heartbeat",
                json={"worker_id": self.worker_id, "sent_at": iso(now_utc())},
            )
            if answer.status_code == 200:
                return answer.json().get("status")
            self.logger.warning("heartbeat rejected", extra={"job_id": job_id, "status": answer.status_code})
        except (httpx.HTTPError, ValueError):
            self.logger.exception("heartbeat failed", extra={"job_id": job_id})
        return None

    def _report(self, job_id: str, status: str, reason: str | None = None) -> None:
        report = {
            "status": status,
            "reported_by": "worker",
            "worker_id": self.worker_id,
            "finished_at": iso(now_utc()),
        }
        if reason:
            report["reason"] = reason[:1000]
        try:
            response = self.http.post(f"{self.job_service}/internal/jobs/{job_id}/status", json=report)
            if response.status_code == 409:
                self.logger.info("terminal status already recorded", extra={"job_id": job_id})
            else:
                response.raise_for_status()
        except httpx.HTTPError:
            self.logger.exception("could not report terminal status", extra={"job_id": job_id})
