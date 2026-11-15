"""The parallelism selector: every rule, its limits, and that its answers fit the job form."""

import json
from dataclasses import astuple
from pathlib import Path

import pytest
from distributed.selector import Workload, select
from jsonschema import Draft202012Validator

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"
JOB_FORM = json.loads((CONTRACTS / "training-job.schema.json").read_text(encoding="utf-8"))

# ResNet-18 on CIFAR-10 for 100 epochs at 2,500 images/s: 33 minutes on one GPU, with four 16 GB GPUs free
JOB = {
    "model_memory_gb": 2,
    "gpu_memory_gb": 16,
    "gpus_available": 4,
    "dataset_images": 50_000,
    "epochs": 100,
    "images_per_second": 2_500,
}


@pytest.mark.parametrize(
    ("changes", "expected"),  # expected: choice, strategy, world_size, gpu_count, jobs
    [
        ({}, ("ddp", "ddp", 4, 4, 1)),  # throughput is the limit and GPUs are free
        ({"epochs": 1}, ("single", "single", 1, 1, 1)),  # a 20-second job: DDP start-up outweighs the gain
        ({"gpus_available": 1}, ("single", "single", 1, 1, 1)),
        ({"gpus_available": 0}, ("single", "single", 1, 0, 1)),  # CPU only
        ({"model_memory_gb": 40}, ("model_parallel", None, 3, 3, 1)),  # 40 GB does not fit in 16 GB
        ({"independent_trials": 8}, ("parallel_trials", "single", 1, 1, 8)),
        ({"budget_gpu_hours": 0.70}, ("ddp", "ddp", 3, 3, 1)),  # 4 GPUs would use 0.76 GPU-hours
        ({"budget_gpu_hours": 0.60}, ("single", "single", 1, 1, 1)),  # only one GPU (0.56 GPU-hours) fits
    ],
)
def test_rules_and_the_job_form_they_lead_to(changes, expected):
    decision = select(Workload(**{**JOB, **changes}))
    example = JOB_FORM["examples"][0]
    form = {
        **example,
        "resources": {**example["resources"], "gpu_count": decision.gpu_count},
        "parallelism": {"strategy": decision.strategy, "world_size": decision.world_size},
    }

    assert astuple(decision)[:5] == expected  # everything but the reason
    # a choice the platform can run today is a valid job form; model parallelism is not one yet
    assert Draft202012Validator(JOB_FORM).is_valid(form) == (decision.strategy is not None)


def test_slow_gradient_sharing_keeps_the_job_on_one_gpu():
    assert select(Workload(**JOB), sync_overhead=0.6).choice == "single"  # 2 GPUs would reach 62% efficiency


def test_world_size_stays_within_the_job_form_limit():
    assert select(Workload(**{**JOB, "gpus_available": 16}), sync_overhead=0.01).world_size == 8


@pytest.mark.parametrize(
    "bad", [{"gpus_available": -1}, {"epochs": 0}, {"images_per_second": 0}, {"independent_trials": 0}]
)
def test_impossible_workloads_are_refused(bad):
    with pytest.raises(ValueError):
        select(Workload(**{**JOB, **bad}))
