"""MLflow lifecycle boundary for one training job attempt."""

import os
from typing import Any

from app.models import TrainingJob


class MlflowTracker:
    def __init__(self, job: TrainingJob) -> None:
        self.job = job
        self._run = None

    def __enter__(self) -> "MlflowTracker":
        import mlflow

        mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
        mlflow.set_experiment(os.environ.get("MLFLOW_EXPERIMENT_NAME", "cloudtrain"))
        self._run = mlflow.start_run(
            run_name=f"{self.job.job_id}-attempt",
            tags={
                "job_id": self.job.job_id,
                "project_id": self.job.project_id,
                "dataset_id": self.job.dataset_id,
                "dataset_version": str(self.job.dataset_version),
                "model": self.job.model,
            },
        )
        return self

    def __exit__(self, error_type, *_: Any) -> None:
        import mlflow

        mlflow.end_run(status="FAILED" if error_type else "FINISHED")

    def log_params(self, params: dict[str, Any]) -> None:
        import mlflow

        mlflow.log_params(params)

    def log_metrics(self, metrics: dict[str, float], step: int | None = None) -> None:
        import mlflow

        mlflow.log_metrics(metrics, step=step)


def tracker_for(job: TrainingJob) -> MlflowTracker:
    return MlflowTracker(job)
