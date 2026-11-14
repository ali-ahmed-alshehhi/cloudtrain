"""Benchmark arithmetic: speedup, efficiency, GPU-hours and cost, and the runs it refuses to compare."""

import pytest
from distributed import metrics


def run(gpus: int, epoch_seconds: list[float], total_seconds: float = 0.0, **changes) -> dict:
    """A result shaped like the ones `train.run` returns, with 50,000 images per epoch."""
    return {
        "model": "resnet18",
        "dataset": "cifar10",
        "train_images": 50_000,
        "epochs": len(epoch_seconds),
        "batch_size": 128,
        "num_workers": 4,
        "gpus": gpus,
        "epochs_detail": [
            {"seconds": seconds, "images": 50_000, "data_wait_seconds": seconds / 10}
            for seconds in epoch_seconds
        ],
        "total_seconds": total_seconds,
        "accuracy": 0.9,
        "sync_probe": None,
        **changes,
    }


ONE_GPU = run(1, [120, 100, 100], total_seconds=360)  # the whole run took 0.1 hours
TWO_GPUS = run(2, [80, 62.5, 62.5], total_seconds=225)  # 0.0625 hours


def test_first_epoch_is_left_out_as_warm_up():
    summary = metrics.summarise(ONE_GPU)

    assert summary["time_per_epoch_s"] == 100
    assert summary["images_per_second"] == 500
    assert summary["data_wait_share"] == pytest.approx(0.1)
    assert metrics.summarise(run(1, [120]))["time_per_epoch_s"] == 120  # unless it is the only epoch


def test_speedup_efficiency_gpu_hours_and_cost():
    single, ddp = metrics.scaling_rows([ONE_GPU, TWO_GPUS], hourly_usd=2.0)

    assert (single["speedup"], single["efficiency"]) == (1.0, 1.0)
    assert ddp["speedup"] == pytest.approx(1.6)  # 100 s / 62.5 s
    assert ddp["efficiency"] == pytest.approx(0.8)  # 1.6 / 2 GPUs
    assert (single["gpu_hours"], ddp["gpu_hours"]) == pytest.approx((0.1, 0.125))  # GPUs x hours of the run
    assert (single["cost_usd"], ddp["cost_usd"]) == pytest.approx((0.2, 0.125))  # hours x 2 USD per hour


def test_repeated_runs_are_averaged():
    rows = metrics.scaling_rows([run(1, [90]), run(1, [110]), run(2, [50])])

    assert [row["repeats"] for row in rows] == [2, 1]
    assert rows[1]["speedup"] == pytest.approx(2.0)  # the mean of 90 s and 110 s, against 50 s
    assert rows[1]["cost_usd"] is None  # no price was given


@pytest.mark.parametrize(
    ("results", "reason"),
    [
        ([ONE_GPU, run(0, [300, 300, 300])], "not GPU scaling"),  # DDP on a CPU shows the code works, no more
        ([ONE_GPU, run(2, [80, 60, 60], batch_size=256)], "batch_size"),  # a different workload
        ([TWO_GPUS], "1-GPU run"),  # nothing to compare against
    ],
)
def test_runs_that_cannot_be_compared_are_refused(results, reason):
    with pytest.raises(ValueError, match=reason):
        metrics.scaling_rows(results)


def test_prices_come_from_the_pricing_contract():
    assert metrics.hourly_price("local-cpu") == 0
    assert metrics.hourly_price("g4dn.12xlarge") > metrics.hourly_price("g4dn.xlarge") > 0


def test_unknown_machine_type_is_refused():
    with pytest.raises(ValueError, match="p9.mega"):
        metrics.hourly_price("p9.mega")


def test_tables_for_the_benchmark_document():
    scaling = metrics.scaling_table(metrics.scaling_rows([ONE_GPU, TWO_GPUS], hourly_usd=2.0))
    workers = metrics.workers_table([run(1, [100], num_workers=0), run(1, [50], num_workers=4)])
    probe = {"steps": 50, "step_seconds": 0.033, "step_seconds_without_sync": 0.030}
    sync = metrics.sync_table([{**TWO_GPUS, "sync_probe": probe}])

    assert scaling.splitlines()[2:] == [
        "| single | 1 | 100.0 s | 360.0 s | 500 | 1.00 | 100% | 0.1000 | 0.2000 | 90.0% |",
        "| ddp | 2 | 62.5 s | 225.0 s | 800 | 1.60 | 80% | 0.1250 | 0.1250 | 90.0% |",
    ]
    assert workers.splitlines()[2:] == ["| 0 | 500 | 100.0 s | 10% |", "| 4 | 1,000 | 50.0 s | 10% |"]
    assert sync.splitlines()[2:] == ["| 2 | 128 | 33.0 ms | 30.0 ms | 3.0 ms | 10% |"]
