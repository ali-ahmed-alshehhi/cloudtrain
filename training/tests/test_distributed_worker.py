"""DDP inside the training worker (#28): the per-epoch timing for the 1 vs N comparison page (#76)."""

import sys
import threading

import pytest
from pydantic import ValidationError

torch = pytest.importorskip("torch", reason="worker DDP tests require PyTorch")
pytest.importorskip("numpy", reason="the tabular job requires NumPy")

from distributed import ddp  # noqa: E402

from app.models import TrainingJob  # noqa: E402
from app.trainer import train_cifar  # noqa: E402

EPOCHS = 3  # the comparison page leaves the first epoch out as warm-up, so it needs at least 3


class MemoryArtifactStore:
    def load_latest(self, *_):
        return None

    def save_checkpoint(self, *_, is_best=False):
        return "memory://checkpoint"

    def save_final(self, job_id, *_):
        return f"memory://jobs/{job_id}/model/model-bundle.pt"


def _job(strategy: str, processes: int) -> TrainingJob:
    return TrainingJob.model_validate(
        {
            "job_id": "job-1",
            "project_id": "project-1",
            "dataset_id": "dataset-1",
            "dataset_version": 1,
            "model": "tabular_mlp",
            # batch size 1, so neither run drops an incomplete last batch and both see every image
            "hyperparameters": {"epochs": EPOCHS, "batch_size": 1, "learning_rate": 0.01, "seed": 3},
            "resources": {"gpu_count": processes, "cpu_cores": 2, "memory_gb": 2},
            "parallelism": {"strategy": strategy, "world_size": processes},
            "execution": {"max_runtime_minutes": 2, "retry_limit": 0},
        }
    )


def _train(job: TrainingJob, dataset_dir, monkeypatch) -> list[tuple[int, dict[str, float]]]:
    (dataset_dir / "wisconsin.csv").write_text(
        "radius,texture,diagnosis\n"
        "1.0,1.0,B\n1.2,0.9,B\n0.8,1.1,B\n1.1,1.2,B\n"
        "8.0,8.0,M\n8.2,7.9,M\n7.8,8.1,M\n8.1,8.2,M\n"
    )
    (dataset_dir / ".cloudtrain-checksum-sha256").write_text("a" * 64)
    real_launch = ddp.launch
    monkeypatch.setattr(  # this laptop has no GPUs: run the processes on the CPU (gloo)
        ddp,
        "launch",
        lambda fn, world_size, args, device: real_launch(fn, world_size, args=args, device="cpu"),
    )
    logged = []
    train_cifar(
        job,
        dataset_dir,
        lambda epoch, metrics: logged.append((epoch, metrics)),
        threading.Event(),
        artifact_store=MemoryArtifactStore(),
    )
    return logged


@pytest.mark.skipif(sys.platform == "win32", reason="DDP process spawning needs Linux, WSL2 or macOS")
def test_single_and_ddp_log_the_time_and_images_of_every_epoch(tmp_path, monkeypatch):
    (tmp_path / "single").mkdir()
    (tmp_path / "ddp").mkdir()

    single = _train(_job("single", 1), tmp_path / "single", monkeypatch)
    distributed = _train(_job("ddp", 2), tmp_path / "ddp", monkeypatch)

    for logged in (single, distributed):
        assert [epoch for epoch, _ in logged] == list(range(1, EPOCHS + 1))  # step = epoch
        for _, metrics in logged:
            assert metrics["epoch_seconds"] > 0
            assert {"train_loss", "validation_loss", "accuracy", "f1"} <= metrics.keys()
    # the DDP run counts the images of both processes, so an epoch covers the same data as the single run
    assert [m["epoch_images"] for _, m in distributed] == [m["epoch_images"] for _, m in single]
    assert single[0][1]["epoch_images"] == 6  # 8 rows, 2 held out for validation


def test_ddp_job_whose_world_size_differs_from_its_gpu_count_is_refused():
    form = _job("ddp", 2).model_dump()
    form["resources"]["gpu_count"] = 1

    with pytest.raises(ValidationError, match="world_size must equal resources.gpu_count"):
        TrainingJob.model_validate(form)
