"""MLflow lifecycle boundary for one training job attempt."""

import os
import platform
from typing import Any

from app.models import TrainingJob


class MlflowTracker:
    def __init__(self, job: TrainingJob, *, mlflow_module=None) -> None:
        self.job = job
        self._run = None
        self._mlflow = mlflow_module

    def __enter__(self) -> "MlflowTracker":
        mlflow = self._module()

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
                "strategy": self.job.parallelism.strategy,
                "world_size": str(self.job.parallelism.world_size),
                **_environment_tags(mlflow),
            },
        )
        return self

    def __exit__(self, error_type, *_: Any) -> None:
        self._module().end_run(status="FAILED" if error_type else "FINISHED")

    def log_params(self, params: dict[str, Any]) -> None:
        self._module().log_params(params)

    def log_metrics(self, metrics: dict[str, float], step: int | None = None) -> None:
        self._module().log_metrics(metrics, step=step)

    def log_tags(self, tags: dict[str, str]) -> None:
        self._module().set_tags(tags)

    def log_model(self, model, input_example) -> None:
        mlflow = self._module()
        signature = mlflow.models.infer_signature(input_example, model_output=None)
        mlflow.pytorch.log_model(
            model,
            artifact_path="model",
            input_example=input_example,
            signature=signature,
        )

    def _module(self):
        if self._mlflow is None:
            import mlflow

            self._mlflow = mlflow
        return self._mlflow


def tracker_for(job: TrainingJob) -> MlflowTracker:
    return MlflowTracker(job)


def _environment_tags(mlflow) -> dict[str, str]:
    import torch

    try:
        import torchvision

        torchvision_version = torchvision.__version__
    except ImportError:
        torchvision_version = "unavailable"
    return {
        "environment.python": platform.python_version(),
        "environment.torch": torch.__version__,
        "environment.torchvision": torchvision_version,
        "environment.mlflow": mlflow.__version__,
    }
