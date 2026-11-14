"""DDP helpers, the reference training loop and the benchmark runner: all the code that starts processes."""

import json
import sys
import time
from pathlib import Path

import pytest

torch = pytest.importorskip("torch", reason="PyTorch is not in training/requirements-dev.txt yet")

from distributed import benchmark, ddp, train  # noqa: E402

NEEDS_LINUX = pytest.mark.skipif(
    sys.platform == "win32", reason="PyTorch for Windows cannot start DDP processes: use WSL2 or Linux"
)
SMALL = {"model": "tiny", "device": "cpu", "train_size": 256, "val_size": 64, "epochs": 2}
SMALL_FLAGS = ["--model", "tiny", "--device", "cpu", "--train-size", "256", "--val-size", "64"]


def _train_and_record(ctx: ddp.Context, folder: str) -> None:
    """Runs in every process: train a one-weight model on 16 numbers, then record what this process saw."""
    numbers = torch.arange(16.0).unsqueeze(1)
    model = ddp.wrap(torch.nn.Linear(1, 1), ctx)
    start = [weight.tolist() for weight in model.parameters()]
    loader = ddp.make_loader(torch.utils.data.TensorDataset(numbers, numbers), 4, ctx, shuffle=True)
    optimizer = torch.optim.SGD(model.parameters(), lr=0.001)
    ddp.set_epoch(loader, 0)
    seen = []
    for inputs, targets in loader:
        seen += inputs.flatten().tolist()
        optimizer.zero_grad()
        torch.nn.functional.mse_loss(model(inputs), targets).backward()
        optimizer.step()
    weights = [weight.tolist() for weight in ddp.unwrap(model).parameters()]
    record = {"seen": seen, "start": start, "weights": weights, "main": ctx.is_main}
    Path(folder, f"rank{ctx.rank}.json").write_text(json.dumps(record))


def _load_with_a_worker_and_record(ctx: ddp.Context, folder: str) -> None:
    numbers = torch.arange(8.0).unsqueeze(1)
    dataset = torch.utils.data.TensorDataset(numbers, numbers)
    loader = ddp.make_loader(dataset, 4, ctx, shuffle=False, num_workers=1)
    record = {
        "start": loader.multiprocessing_context.get_start_method(),
        "batches": [inputs.flatten().tolist() for inputs, _ in loader],
    }
    Path(folder, "workers.json").write_text(json.dumps(record))


def _fail(ctx: ddp.Context) -> None:
    raise RuntimeError("out of memory")


def _fail_in_one_process(ctx: ddp.Context) -> None:
    if ctx.rank == 1:
        raise RuntimeError("out of memory")
    time.sleep(60)


def test_single_trains_and_reports():
    result = train.run(train.TrainConfig(**SMALL))

    assert (result["gpus"], result["backend"], result["steps_per_epoch"]) == (0, None, 8)
    assert [epoch["images"] for epoch in result["epochs_detail"]] == [256, 256]
    assert 0 <= result["accuracy"] <= 1
    assert result["total_seconds"] > sum(epoch["seconds"] for epoch in result["epochs_detail"])


@NEEDS_LINUX
def test_ddp_trains_reports_and_measures_gradient_sync():
    result = train.run(train.TrainConfig(**SMALL, strategy="ddp", world_size=2, sync_probe_steps=2))

    assert (result["backend"], result["steps_per_epoch"]) == ("gloo", 4)  # each process takes half the steps
    assert [epoch["images"] for epoch in result["epochs_detail"]] == [256, 256]  # together: every image
    assert result["sync_probe"]["step_seconds"] > 0
    assert result["sync_probe"]["step_seconds_without_sync"] > 0


@NEEDS_LINUX
def test_ddp_splits_the_data_and_keeps_the_models_identical(tmp_path):
    ddp.launch(_train_and_record, 2, args=(str(tmp_path),), device="cpu")

    first, second = (json.loads((tmp_path / f"rank{rank}.json").read_text()) for rank in (0, 1))
    assert not set(first["seen"]) & set(second["seen"])  # each process read its own half
    assert sorted(first["seen"] + second["seen"]) == list(range(16))  # and nothing was left out
    assert first["weights"] == second["weights"] != first["start"]  # both trained, and to the same model
    assert (first["main"], second["main"]) == (True, False)  # exactly one process logs and saves


@pytest.mark.skipif(sys.platform == "win32", reason="Windows has no fork: its workers can only be spawned")
def test_data_workers_are_forked_inside_a_training_process(tmp_path):
    ddp.launch(_load_with_a_worker_and_record, 1, args=(str(tmp_path),), device="cpu")

    record = json.loads((tmp_path / "workers.json").read_text())
    assert record["start"] == "fork"  # spawned, every worker would import PyTorch again and copy the dataset
    assert record["batches"] == [[0, 1, 2, 3], [4, 5, 6, 7]]


@pytest.mark.parametrize(
    "bad",
    [
        {"strategy": "single", "world_size": 2},
        {"strategy": "ddp", "world_size": 1},
        {"strategy": "pipeline"},  # not in the job form yet
        {"epochs": 0},
        {"dataset": "cifar10"},  # no data_dir
    ],
)
def test_config_that_breaks_the_job_form_rules_is_refused(bad):
    with pytest.raises(ValueError):
        train.TrainConfig(**bad)


def test_job_that_needs_more_gpus_than_the_machine_has_is_refused():
    with pytest.raises(RuntimeError, match="needs 99 GPU"):
        ddp.launch(_fail, 99, device="cuda")


def test_error_in_the_training_process_reaches_the_caller():
    with pytest.raises(torch.multiprocessing.ProcessRaisedException, match="out of memory"):
        ddp.launch(_fail, 1, device="cpu")


@NEEDS_LINUX
def test_one_failed_process_stops_the_others():
    start = time.monotonic()
    with pytest.raises(torch.multiprocessing.ProcessRaisedException, match="out of memory"):
        ddp.launch(_fail_in_one_process, 2, device="cpu")

    assert time.monotonic() - start < 30  # left alone, the other process would sleep for 60 seconds


def test_workers_benchmark_saves_every_run_and_prints_the_table(tmp_path, capsys):
    out = tmp_path / "workers.json"
    benchmark.main(["workers", "--values", "0", "1", "--out", str(out), *SMALL_FLAGS])
    table = capsys.readouterr().out.splitlines()[-2:]
    benchmark.main(["report", str(out)])

    assert [result["num_workers"] for result in json.loads(out.read_text())["results"]] == [0, 1]
    assert [row.split(" | ")[0] for row in table] == ["| 0", "| 1"]  # one row per number of workers
    assert capsys.readouterr().out.splitlines()[-2:] == table  # `report` rebuilds it from the saved file


def test_cpu_runs_are_never_reported_as_gpu_scaling(tmp_path):
    out = tmp_path / "scaling.json"
    with pytest.raises(ValueError, match="not GPU scaling"):
        benchmark.main(["scaling", "--gpus", "1", "--repeats", "1", "--out", str(out), *SMALL_FLAGS])

    assert len(json.loads(out.read_text())["results"]) == 1  # the measurement itself is kept
