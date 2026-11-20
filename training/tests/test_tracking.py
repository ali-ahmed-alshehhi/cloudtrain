"""MLflow boundary tests use a fake module, never a live tracking server."""

from types import SimpleNamespace

from app.models import TrainingJob
from app.tracking import MlflowTracker


class FakeMlflow:
    __version__ = "3.18.0"

    def __init__(self) -> None:
        self.tags = {}
        self.models = SimpleNamespace(infer_signature=lambda inputs, model_output=None: "signature")
        self.pytorch = SimpleNamespace(log_model=self._log_model)

    def set_tracking_uri(self, uri):
        self.uri = uri

    def set_experiment(self, name):
        self.experiment = name

    def start_run(self, **kwargs):
        self.tags.update(kwargs["tags"])
        return object()

    def end_run(self, **_):
        pass

    def log_params(self, _):
        pass

    def log_metrics(self, _, step=None):
        pass

    def set_tags(self, tags):
        self.tags.update(tags)

    def _log_model(self, model, **kwargs):
        self.logged_model = (model, kwargs)


def _job() -> TrainingJob:
    return TrainingJob.model_validate(
        {
            "job_id": "job-1",
            "project_id": "project-1",
            "dataset_id": "dataset-1",
            "dataset_version": 1,
            "model": "tabular_mlp",
            "hyperparameters": {
                "epochs": 1,
                "batch_size": 2,
                "learning_rate": 0.01,
            },
            "resources": {"gpu_count": 0, "cpu_cores": 1, "memory_gb": 1},
            "parallelism": {"strategy": "single", "world_size": 1},
            "execution": {"max_runtime_minutes": 1, "retry_limit": 0},
        }
    )


def test_tracker_tags_strategy_and_logs_model_at_required_path(monkeypatch):
    fake = FakeMlflow()
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://mlflow")
    monkeypatch.setattr("app.tracking._environment_tags", lambda _: {"environment.python": "test"})

    with MlflowTracker(_job(), mlflow_module=fake) as tracker:
        tracker.log_tags({"dataset_checksum": "abc"})
        tracker.log_model("model", [[1.0, 2.0]])

    assert fake.tags["strategy"] == "single"
    assert fake.tags["world_size"] == "1"
    assert fake.tags["dataset_checksum"] == "abc"
    assert fake.logged_model[1]["artifact_path"] == "model"
    assert fake.logged_model[1]["signature"] == "signature"
