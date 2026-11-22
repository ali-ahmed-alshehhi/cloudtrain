"""Focused Day 2 tests: storage ordering, compatibility, reproducibility, and tabular bundles."""

import io
import sys
import threading
from pathlib import Path

import pytest

pytest.importorskip("numpy", reason="Day 2 tabular tests require NumPy")
torch = pytest.importorskip("torch", reason="Day 2 training tests require PyTorch")

from distributed import ddp  # noqa: E402

from app.models import TrainingJob  # noqa: E402
from app.reproducibility import seed_everything  # noqa: E402
from app.tabular import load_tabular_data, make_model_bundle  # noqa: E402
from app.trainer import train_cifar  # noqa: E402


def _write_csv(path: Path) -> None:
    path.write_text(
        "radius,texture,diagnosis\n"
        "1.0,1.0,B\n1.2,0.9,B\n0.8,1.1,B\n1.1,1.2,B\n"
        "8.0,8.0,M\n8.2,7.9,M\n7.8,8.1,M\n8.1,8.2,M\n"
    )


def test_tabular_split_and_train_only_standardization_are_deterministic(tmp_path):
    csv_path = tmp_path / "wisconsin.csv"
    _write_csv(csv_path)
    first = load_tabular_data(csv_path, target_column="diagnosis", seed=17, validation_fraction=0.25)
    second = load_tabular_data(csv_path, target_column="diagnosis", seed=17, validation_fraction=0.25)

    assert torch.equal(first.train_inputs, second.train_inputs)
    assert torch.equal(first.validation_inputs, second.validation_inputs)
    assert torch.allclose(first.train_inputs.mean(dim=0), torch.zeros(2), atol=1e-6)
    assert first.feature_names == ["radius", "texture"]
    assert first.class_labels == ["B", "M"]


def test_model_bundle_is_loadable_and_contains_inference_schema(tmp_path):
    csv_path = tmp_path / "wisconsin.csv"
    _write_csv(csv_path)
    data = load_tabular_data(csv_path, target_column="diagnosis", seed=2, validation_fraction=0.25)
    model = torch.nn.Sequential(torch.nn.Linear(2, 2))

    payload = make_model_bundle(model, data, target_column="diagnosis")
    bundle = torch.load(io.BytesIO(payload), weights_only=False)

    assert bundle["preprocessing"]["feature_mean"] == data.feature_mean.tolist()
    assert bundle["class_labels"] == ["B", "M"]
    assert bundle["input_schema"] == {"radius": "float32", "texture": "float32"}


def test_seed_everything_repeats_python_numpy_and_torch():
    import random

    import numpy as np

    seed_everything(91)
    first = (random.random(), np.random.random(), torch.rand(1).item())
    seed_everything(91)
    second = (random.random(), np.random.random(), torch.rand(1).item())

    assert first == second
    assert torch.backends.cudnn.benchmark is False


class MemoryArtifactStore:
    def __init__(self) -> None:
        self.checkpoints = []
        self.final = None

    def load_latest(self, *_):
        return None

    def save_checkpoint(self, job_id, epoch, payload, metadata, *, is_best=False):
        self.checkpoints.append((job_id, epoch, payload, metadata, is_best))

    def save_final(self, job_id, payload, metadata):
        self.final = (job_id, payload, metadata)
        return f"s3://artifacts/jobs/{job_id}/model/model-bundle.pt"


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="CPU DDP worker integration requires Gloo process spawning; use WSL2/Linux or macOS",
)
def test_tabular_worker_ddp_records_once_on_rank_zero(tmp_path, monkeypatch):
    csv_path = tmp_path / "wisconsin.csv"
    _write_csv(csv_path)
    (tmp_path / ".cloudtrain-checksum-sha256").write_text("a" * 64)
    job = TrainingJob.model_validate(
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
                "seed": 7,
            },
            "resources": {"gpu_count": 2, "cpu_cores": 2, "memory_gb": 2},
            "parallelism": {"strategy": "ddp", "world_size": 2},
            "execution": {"max_runtime_minutes": 2, "retry_limit": 0},
        }
    )
    real_launch = ddp.launch
    monkeypatch.setattr(
        ddp,
        "launch",
        lambda fn, world_size, args, device: real_launch(fn, world_size, args=args, device="cpu"),
    )
    store = MemoryArtifactStore()
    epoch_metrics = []

    result = train_cifar(
        job,
        tmp_path,
        lambda epoch, metrics: epoch_metrics.append((epoch, metrics)),
        threading.Event(),
        artifact_store=store,
    )

    assert len(epoch_metrics) == len(store.checkpoints) == 1
    assert store.final is not None
    assert result.artifact_uri.endswith("/model/model-bundle.pt")
    assert {"train_loss", "validation_loss", "accuracy", "f1"} <= result.metrics.keys()
