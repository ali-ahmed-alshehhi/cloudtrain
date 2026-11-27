"""DDP inside the training worker (#28): the per-epoch timing for the 1 vs N comparison page (#76)."""

import sys
import threading

import pytest
from pydantic import ValidationError

torch = pytest.importorskip("torch", reason="worker DDP tests require PyTorch")
pytest.importorskip("numpy", reason="the tabular job requires NumPy")

from distributed import ddp  # noqa: E402

from app.models import TrainingJob  # noqa: E402
from app.trainer import DatasetTooSmall, _require_a_full_batch, train_cifar  # noqa: E402

EPOCHS = 3  # the comparison page leaves the first epoch out as warm-up, so it needs at least 3


class MemoryArtifactStore:
    def load_latest(self, *_):
        return None

    def save_checkpoint(self, *_, is_best=False):
        return "memory://checkpoint"

    def save_final(self, job_id, *_):
        return f"memory://jobs/{job_id}/model/model-bundle.pt"


def _job(strategy: str, processes: int, batch_size: int = 1) -> TrainingJob:
    return TrainingJob.model_validate(
        {
            "job_id": "job-1",
            "project_id": "project-1",
            "dataset_id": "dataset-1",
            "dataset_version": 1,
            "model": "tabular_mlp",
            # batch size 1 by default, so neither run drops an incomplete last batch and both see every image
            "hyperparameters": {"epochs": EPOCHS, "batch_size": batch_size, "learning_rate": 0.01, "seed": 3},
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


# ---------- a dataset too small for the job (found by demo step 8, #177) ----------


@pytest.mark.skipif(sys.platform == "win32", reason="DDP process spawning needs Linux, WSL2 or macOS")
def test_ddp_job_whose_processes_get_no_full_batch_fails_with_a_one_line_reason(tmp_path, monkeypatch):
    # 8 rows, 2 held out: 6 for training, 3 per process, fewer than batch_size 4.
    # Before the check, every process trained no step and train_loss divided by zero.
    with pytest.raises(RuntimeError) as failed:
        _train(_job("ddp", 2, batch_size=4), tmp_path, monkeypatch)

    reason = str(failed.value)  # what Training Jobs receives as the FAILED reason
    assert "\n" not in reason and "Traceback" not in reason
    assert "DatasetTooSmall" in reason
    assert "6 training rows over 2 processes is 3 per process, fewer than batch_size 4" in reason


def test_single_job_with_fewer_rows_than_one_batch_is_refused(tmp_path, monkeypatch):
    with pytest.raises(DatasetTooSmall, match="6 training rows, fewer than batch_size 8"):
        _train(_job("single", 1, batch_size=8), tmp_path, monkeypatch)


@pytest.mark.parametrize(
    ("rows", "world_size", "batch_size", "enough"),
    [
        (6, 1, 6, True),  # exactly one batch
        (5, 1, 6, False),
        (6, 2, 3, True),  # 3 per process
        (5, 2, 3, True),  # ceil(5 / 2) = 3: the sampler pads the shorter share
        (4, 2, 3, False),  # 2 per process
        (455, 2, 16, True),  # the Wisconsin comparison of #30
    ],
)
def test_a_job_needs_one_full_batch_in_every_process(rows, world_size, batch_size, enough):
    if enough:
        _require_a_full_batch(rows, world_size, batch_size)
    else:
        with pytest.raises(DatasetTooSmall):
            _require_a_full_batch(rows, world_size, batch_size)
