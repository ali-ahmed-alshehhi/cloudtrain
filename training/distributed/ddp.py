"""DistributedDataParallel (DDP) helpers: one training process per GPU, all on one machine.

Write the training function once; it then runs as `single` (one process) or `ddp` (several processes
that average their gradients after every step):

    def train(ctx, job):                                   # runs in every process
        model = ddp.wrap(build_model().to(ctx.device), ctx)
        loader = ddp.make_loader(dataset, batch_size, ctx, shuffle=True, num_workers=4)
        for epoch in range(epochs):
            ddp.set_epoch(loader, epoch)
            ...                                            # the usual training loop
        if ctx.is_main:
            save(ddp.unwrap(model))                        # exactly one process logs and saves

    ddp.launch(train, world_size, args=(job,))             # world_size comes from the job form
"""

import socket
from collections.abc import Callable
from dataclasses import dataclass

import torch
import torch.distributed as dist
import torch.multiprocessing as mp
from torch.nn.parallel import DistributedDataParallel
from torch.utils.data import DataLoader, Dataset
from torch.utils.data.distributed import DistributedSampler


@dataclass(frozen=True)
class Context:
    """What one training process knows about its place in the job."""

    rank: int  # 0 .. world_size - 1
    world_size: int
    device: torch.device
    backend: str | None  # how the processes talk: "nccl" between GPUs, "gloo" on CPU, None when alone

    @property
    def distributed(self) -> bool:
        return self.world_size > 1

    @property
    def is_main(self) -> bool:
        """True in exactly one process: the one that logs, evaluates and saves."""
        return self.rank == 0


def launch(fn: Callable, world_size: int, args: tuple = (), device: str = "auto") -> None:
    """Run `fn(ctx, *args)` in `world_size` new processes and wait for them to finish.

    `device` is "auto" (GPUs when the machine has them), "cuda" or "cpu". A GPU job gets one GPU per
    process and is refused when the machine has fewer. If one process fails, the others are stopped
    and its error is raised here.
    """
    if world_size < 1:
        raise ValueError(f"world_size must be at least 1, got {world_size}")
    if device not in ("auto", "cuda", "cpu"):
        raise ValueError(f"device must be auto, cuda or cpu, got {device!r}")
    gpus = torch.cuda.device_count() if torch.cuda.is_available() else 0
    use_gpu = device == "cuda" or (device == "auto" and gpus > 0)
    if use_gpu and world_size > gpus:
        raise RuntimeError(f"this job needs {world_size} GPU(s), one per process, but the machine has {gpus}")
    mp.spawn(_process, args=(fn, world_size, _free_port(), use_gpu, args), nprocs=world_size, join=True)


def _process(rank: int, fn: Callable, world_size: int, port: int, use_gpu: bool, args: tuple) -> None:
    device = torch.device("cuda", rank) if use_gpu else torch.device("cpu")
    backend = None
    if world_size > 1:
        backend = "nccl" if use_gpu and dist.is_nccl_available() else "gloo"
        dist.init_process_group(
            backend, init_method=f"tcp://127.0.0.1:{port}", rank=rank, world_size=world_size
        )
    fn(Context(rank, world_size, device, backend), *args)
    if world_size > 1:  # only after success: a failed process just exits and `launch` stops the others
        dist.destroy_process_group()


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def wrap(model: torch.nn.Module, ctx: Context) -> torch.nn.Module:
    """The model itself when alone; under DDP a wrapper that averages gradients across the processes."""
    if not ctx.distributed:
        return model
    return DistributedDataParallel(
        model, device_ids=[ctx.device.index] if ctx.device.type == "cuda" else None
    )


def unwrap(model: torch.nn.Module) -> torch.nn.Module:
    """The plain model again, for evaluating or saving (a DDP wrapper keeps it in `.module`)."""
    return model.module if isinstance(model, DistributedDataParallel) else model


def worker_context(num_workers: int) -> str | None:
    """How DataLoader workers start, for `multiprocessing_context`: forked, where the platform can.

    `launch` starts the training processes with spawn, and a process started that way would spawn its
    workers too: each one a new Python that imports PyTorch again and receives its own copy of the dataset,
    one after the other. With CIFAR-10 that took 2.7 s per worker; forked workers start at once.
    """
    return "fork" if num_workers > 0 and "fork" in mp.get_all_start_methods() else None


def make_loader(
    dataset: Dataset, batch_size: int, ctx: Context, *, shuffle: bool, num_workers: int = 0, seed: int = 0
) -> DataLoader:
    """A training DataLoader. `batch_size` is per process, so one step uses batch_size x world_size samples.

    Under DDP every process reads its own share of the dataset. The last incomplete batch is dropped,
    which keeps the number of steps equal in all processes (unequal counts would make DDP hang).
    """
    sampler = DistributedSampler(dataset, shuffle=shuffle, seed=seed) if ctx.distributed else None
    return DataLoader(
        dataset,
        batch_size=batch_size,
        sampler=sampler,
        shuffle=shuffle and sampler is None,
        generator=torch.Generator().manual_seed(seed),
        num_workers=num_workers,
        multiprocessing_context=worker_context(num_workers),
        persistent_workers=num_workers > 0,
        pin_memory=ctx.device.type == "cuda",
        drop_last=True,
    )


def set_epoch(loader: DataLoader, epoch: int) -> None:
    """Call at the start of every epoch: without it DDP repeats the same sample order each epoch."""
    if isinstance(loader.sampler, DistributedSampler):
        loader.sampler.set_epoch(epoch)
