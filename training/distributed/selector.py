"""The parallelism selector: which strategy a training job should use, and why.

Rules, checked in this order (TEAM_GUIDE.md, section 12):

1. The model does not fit on one GPU   -> model parallelism (tensor / pipeline). The job form does not
                                          accept these yet, so the platform cannot run the job today.
2. Several independent experiments     -> parallel trials: one `single` job per trial.
3. Fewer than two GPUs to use          -> single.
4. Otherwise                           -> DDP on the most GPUs that still pay off; single when none does.

"Pay off" is where communication overhead, dataset size and budget come in. The time on n GPUs is
predicted as

    time(n) = time(1) x (1 + sync_overhead x (n - 1)) / n + start-up time

and DDP on n GPUs is accepted only when it keeps `min_efficiency` of the ideal n-times speedup and
fits the GPU-hour budget. A small dataset means a short job, where the start-up time eats the gain.
"""

import math
from dataclasses import dataclass

MAX_WORLD_SIZE = 8  # the largest world_size the job form allows


@dataclass(frozen=True)
class Workload:
    """What is known about a job before it runs."""

    model_memory_gb: float  # GPU memory one copy of the model needs while training
    gpu_memory_gb: float  # memory of one GPU on the target machine
    gpus_available: int  # GPUs the Scheduler can give this job (0 = CPU only)
    dataset_images: int  # training samples per epoch
    epochs: int
    images_per_second: float  # measured throughput of this model on one GPU (docs/BENCHMARKS.md)
    independent_trials: int = 1  # more than 1: a search made of runs that do not depend on each other
    budget_gpu_hours: float | None = None  # the most GPU-hours the job may use


@dataclass(frozen=True)
class Decision:
    choice: str  # "single", "ddp", "parallel_trials" or "model_parallel"
    strategy: (
        str | None
    )  # parallelism.strategy for the job form; None when the form cannot express the choice
    world_size: int  # parallelism.world_size of each job
    gpu_count: int  # resources.gpu_count of each job
    jobs: int  # how many jobs to submit
    reason: str


def select(
    work: Workload,
    *,
    sync_overhead: float = 0.10,
    startup_seconds: float = 30.0,
    min_efficiency: float = 0.70,
) -> Decision:
    """Choose the strategy for `work`.

    `sync_overhead` is what sharing gradients adds to a training step for each extra GPU, as a share
    of the step (the "Sync overhead" column of docs/BENCHMARKS.md, section 4). `startup_seconds` is
    what a DDP job spends before its first step. Both defaults are assumptions until the cloud
    benchmark replaces them.
    """
    if work.gpus_available < 0 or work.independent_trials < 1 or work.epochs < 1 or work.dataset_images < 1:
        raise ValueError(
            "gpus_available cannot be negative; trials, epochs and dataset_images must be at least 1"
        )
    if min(work.model_memory_gb, work.gpu_memory_gb, work.images_per_second) <= 0:
        raise ValueError("model_memory_gb, gpu_memory_gb and images_per_second must be positive")

    one_gpu = min(1, work.gpus_available)
    if work.gpus_available and work.model_memory_gb > work.gpu_memory_gb:
        needed = math.ceil(work.model_memory_gb / work.gpu_memory_gb)
        return Decision(
            choice="model_parallel",
            strategy=None,
            world_size=needed,
            gpu_count=needed,
            jobs=1,
            reason=f"the model needs {work.model_memory_gb:g} GB but one GPU has {work.gpu_memory_gb:g} GB. "
            f"Only splitting the model over {needed} GPUs (tensor or pipeline parallelism) can train it; "
            "DDP cannot, because every DDP process holds a full copy. The job form does not accept "
            "these strategies yet.",
        )
    if work.independent_trials > 1:
        return Decision(
            choice="parallel_trials",
            strategy="single",
            world_size=1,
            gpu_count=one_gpu,
            jobs=work.independent_trials,
            reason=f"{work.independent_trials} independent trials share nothing, so one single job per trial "
            "scales with no communication cost; DDP would add gradient sharing to every step of every trial.",
        )
    if work.gpus_available < 2:
        return Decision(
            choice="single",
            strategy="single",
            world_size=1,
            gpu_count=one_gpu,
            jobs=1,
            reason="fewer than two GPUs are available, so DDP is not possible.",
        )

    hours = work.dataset_images * work.epochs / work.images_per_second / 3600
    for gpus in range(min(work.gpus_available, MAX_WORLD_SIZE), 1, -1):  # most GPUs first: more is faster
        ddp_hours = hours * (1 + sync_overhead * (gpus - 1)) / gpus + startup_seconds / 3600
        efficiency = hours / ddp_hours / gpus
        over_budget = work.budget_gpu_hours is not None and gpus * ddp_hours > work.budget_gpu_hours
        if efficiency >= min_efficiency and not over_budget:
            return Decision(
                choice="ddp",
                strategy="ddp",
                world_size=gpus,
                gpu_count=gpus,
                jobs=1,
                reason=f"throughput is the limit: {gpus} GPUs should cut {hours * 60:.1f} minutes to "
                f"{ddp_hours * 60:.1f} ({efficiency:.0%} efficiency, {gpus * ddp_hours:.2f} GPU-hours).",
            )
    return Decision(  # one GPU also uses the fewest GPU-hours, so it is the answer when the budget is tight
        choice="single",
        strategy="single",
        world_size=1,
        gpu_count=1,
        jobs=1,
        reason=f"the job takes about {hours * 60:.1f} minutes on one GPU, and no DDP setting keeps "
        f"{min_efficiency:.0%} efficiency within the budget: start-up and gradient sharing would cost "
        "more than they save.",
    )
