"""The single vs DDP comparison through the platform (#30): its job forms and its arithmetic."""

import pytest
from distributed.platform_compare import job_form, main, summarise, table

from app.models import JobSubmission


def test_single_and_ddp_forms_follow_the_contract_and_differ_only_in_strategy():
    single = job_form("project-1", "dataset-1", processes=1, seed=0, epochs=10, batch_size=16)
    ddp = job_form("project-1", "dataset-1", processes=2, seed=0, epochs=10, batch_size=16)

    JobSubmission.model_validate(single)
    JobSubmission.model_validate(ddp)  # for ddp, world_size = gpu_count
    assert ddp["parallelism"] == {"strategy": "ddp", "world_size": 2}
    assert single["hyperparameters"] == ddp["hyperparameters"]  # the comparison page needs the same workload


def _run(processes: int, seconds: list[float]) -> dict:
    return {
        "processes": processes,
        "epoch_seconds": seconds,
        "epoch_images": [400.0] * len(seconds),
        "wall_seconds": 4.0,
        "gpu_hours": 0.001 * processes,
        "accuracy": 0.9,
    }


def test_first_epoch_is_left_out_and_speedup_is_against_one_process():
    single, ddp = _run(1, [9.0, 0.02, 0.02]), _run(2, [9.0, 0.01, 0.01])

    assert summarise(single) == {"time_per_epoch_s": 0.02, "images_per_second": pytest.approx(20_000)}
    markdown = table([single, ddp], "2 processes on CPU, local stack")
    assert "Measured: 2 processes on CPU, local stack." in markdown
    assert "| ddp | 2 | 1 | 10.0 | 40,000 | 2.00 | 100% |" in markdown


def test_fewer_than_three_epochs_is_refused(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "sys.argv",
        [
            "platform_compare",
            "--csv",
            "x.csv",
            "--label",
            "x",
            "--out",
            str(tmp_path / "o.json"),
            "--epochs",
            "2",
        ],
    )
    with pytest.raises(SystemExit):
        main()
