"""Reference training loop on top of `ddp`: the benchmark workload, and a worked example of the helpers.

    python -m distributed.train --strategy ddp --world-size 2 --dataset cifar10 --data-dir /data

The same loop runs as `single` or `ddp` and returns one result: the time of every epoch, the images
processed, the time spent waiting for data, the final accuracy and (for ddp) the gradient-sync time.
"""

import argparse
import contextlib
import copy
import json
import os
import platform
import tempfile
import time
from dataclasses import asdict, dataclass, fields
from pathlib import Path

import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

from . import ddp

CLASSES = 10  # CIFAR-10, and the synthetic images that stand in for it


@dataclass(frozen=True)
class TrainConfig:
    strategy: str = "single"  # the job form's parallelism.strategy
    world_size: int = 1  # the job form's parallelism.world_size (= resources.gpu_count for ddp)
    model: str = "resnet18"  # "tiny" or any torchvision classification model
    dataset: str = "synthetic"  # "synthetic" (nothing to download) or "cifar10"
    data_dir: str | None = None  # folder that holds CIFAR-10 in torchvision's layout
    epochs: int = 1
    batch_size: int = 32  # per process; one step uses batch_size x world_size images
    learning_rate: float = 0.05
    num_workers: int = 0  # DataLoader worker processes per training process
    device: str = "auto"  # auto, cuda or cpu
    seed: int = 0
    train_size: int = 50_000  # synthetic dataset only
    val_size: int = 10_000  # synthetic dataset only
    sync_probe_steps: int = 0  # ddp only: time this many steps with and without gradient sharing

    def __post_init__(self) -> None:
        # the same rules as contracts/training-job.schema.json
        if self.strategy not in ("single", "ddp"):
            raise ValueError(f"strategy must be single or ddp, got {self.strategy!r}")
        if self.strategy == "single" and self.world_size != 1:
            raise ValueError("strategy single needs world_size 1")
        if self.strategy == "ddp" and self.world_size < 2:
            raise ValueError("strategy ddp needs world_size 2 or more")
        if self.epochs < 1 or self.batch_size < 1:
            raise ValueError("epochs and batch_size must be at least 1")
        if self.dataset == "cifar10" and not self.data_dir:
            raise ValueError("dataset cifar10 needs data_dir, the folder that holds the downloaded dataset")


class SyntheticImages(Dataset):
    """Images shaped like CIFAR-10, made on the fly: every class is a fixed random pattern under noise.

    Nothing to download, and a model can learn the patterns, so accuracy still means something.
    """

    def __init__(self, size: int, seed: int) -> None:
        self.size, self.seed = size, seed
        # seed 0 for the patterns: training and validation images must show the same classes
        self.patterns = torch.randn(CLASSES, 3, 32, 32, generator=torch.Generator().manual_seed(0))

    def __len__(self) -> int:
        return self.size

    def __getitem__(self, index: int) -> tuple[torch.Tensor, int]:
        label = index % CLASSES
        noise = torch.randn(3, 32, 32, generator=torch.Generator().manual_seed(self.seed * 1_000_003 + index))
        return 0.1 * self.patterns[label] + noise, label


def build_datasets(cfg: TrainConfig) -> tuple[Dataset, Dataset]:
    if cfg.dataset == "synthetic":
        return SyntheticImages(cfg.train_size, seed=1), SyntheticImages(cfg.val_size, seed=2)
    if cfg.dataset == "cifar10":
        from torchvision import datasets
        from torchvision.transforms import v2

        to_tensor = [
            v2.ToImage(),
            v2.ToDtype(torch.float32, scale=True),
            v2.Normalize((0.4914, 0.4822, 0.4465), (0.2470, 0.2435, 0.2616)),
        ]
        augment = v2.Compose([v2.RandomCrop(32, padding=4), v2.RandomHorizontalFlip(), *to_tensor])
        return (
            datasets.CIFAR10(cfg.data_dir, train=True, transform=augment),
            datasets.CIFAR10(cfg.data_dir, train=False, transform=v2.Compose(to_tensor)),
        )
    raise ValueError(f"dataset must be synthetic or cifar10, got {cfg.dataset!r}")


def build_model(name: str) -> nn.Module:
    if name == "tiny":  # three layers for 32x32 images: quick on a CPU, and too small to gain from DDP
        return nn.Sequential(
            nn.Conv2d(3, 16, 3, stride=2, padding=1),
            nn.ReLU(),
            nn.Conv2d(16, 32, 3, stride=2, padding=1),
            nn.ReLU(),
            nn.Flatten(),
            nn.Linear(32 * 8 * 8, CLASSES),
        )
    import torchvision

    return torchvision.models.get_model(name, weights=None, num_classes=CLASSES)


def run(cfg: TrainConfig) -> dict:
    """Train once in fresh processes and return the measurements."""
    with tempfile.TemporaryDirectory() as folder:
        out = Path(folder) / "result.json"
        start = time.perf_counter()
        ddp.launch(_train, cfg.world_size, args=(cfg, str(out)), device=cfg.device)
        total_seconds = time.perf_counter() - start  # includes starting the processes and the evaluation
        return {**json.loads(out.read_text()), "total_seconds": total_seconds}


def _train(ctx: ddp.Context, cfg: TrainConfig, out: str) -> None:
    torch.manual_seed(cfg.seed)
    torch.backends.cudnn.benchmark = True
    train_set, val_set = build_datasets(cfg)
    model = ddp.wrap(build_model(cfg.model).to(ctx.device), ctx)
    loader = ddp.make_loader(
        train_set, cfg.batch_size, ctx, shuffle=True, num_workers=cfg.num_workers, seed=cfg.seed
    )
    optimizer = torch.optim.SGD(model.parameters(), lr=cfg.learning_rate, momentum=0.9)
    loss_fn = nn.CrossEntropyLoss()

    epochs = []
    for epoch in range(cfg.epochs):
        ddp.set_epoch(loader, epoch)
        model.train()
        data_wait = 0.0
        start = waiting_since = _now(ctx)
        for images, labels in loader:
            data_wait += time.perf_counter() - waiting_since
            images = images.to(ctx.device, non_blocking=True)
            labels = labels.to(ctx.device, non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            loss_fn(model(images), labels).backward()
            optimizer.step()
            waiting_since = time.perf_counter()
        seconds = _now(ctx) - start
        seen = len(loader) * cfg.batch_size * cfg.world_size  # every process ran len(loader) steps
        epochs.append({"seconds": seconds, "images": seen, "data_wait_seconds": data_wait})

    sync_probe = None
    if ctx.distributed and cfg.sync_probe_steps:
        sync_probe = _probe_sync(model, loader, loss_fn, ctx, cfg.sync_probe_steps)
    if ctx.is_main:
        result = {
            **asdict(cfg),
            "gpus": cfg.world_size if ctx.device.type == "cuda" else 0,
            "backend": ctx.backend,
            "train_images": len(train_set),
            "steps_per_epoch": len(loader),
            "epochs_detail": epochs,
            "accuracy": _accuracy(ddp.unwrap(model), val_set, cfg, ctx),
            "sync_probe": sync_probe,
            "environment": _environment(ctx),
        }
        Path(out).write_text(json.dumps(result))


def _now(ctx: ddp.Context) -> float:
    """The time once the GPU has finished what it was given (GPU work runs in the background)."""
    if ctx.device.type == "cuda":
        torch.cuda.synchronize(ctx.device)
    return time.perf_counter()


def _probe_sync(
    model: nn.Module, loader: DataLoader, loss_fn: nn.Module, ctx: ddp.Context, steps: int
) -> dict:
    """Time `steps` training steps with gradient sharing and again without it, on one fixed batch.

    The difference is what DDP spends on communication in every step. The model is left as it was.
    """
    images, labels = next(iter(loader))
    images, labels = images.to(ctx.device), labels.to(ctx.device)
    before = copy.deepcopy(model.state_dict())  # no optimizer runs here, but BatchNorm statistics still move

    def seconds_per_step(share: bool) -> float:
        start = _now(ctx)
        with contextlib.nullcontext() if share else model.no_sync():
            for _ in range(steps):
                model.zero_grad(set_to_none=True)
                loss_fn(model(images), labels).backward()
        return (_now(ctx) - start) / steps

    seconds_per_step(True)  # warm-up
    with_sync, without_sync = seconds_per_step(True), seconds_per_step(False)
    model.load_state_dict(before)
    return {"steps": steps, "step_seconds": with_sync, "step_seconds_without_sync": without_sync}


def _accuracy(model: nn.Module, dataset: Dataset, cfg: TrainConfig, ctx: ddp.Context) -> float:
    """Share of validation images classified correctly, counted by one process so each image counts once."""
    loader = DataLoader(
        dataset,
        batch_size=cfg.batch_size,
        num_workers=cfg.num_workers,
        multiprocessing_context=ddp.worker_context(cfg.num_workers),
        pin_memory=ctx.device.type == "cuda",
    )
    model.eval()
    correct = 0
    with torch.no_grad():
        for images, labels in loader:
            predicted = model(images.to(ctx.device)).argmax(dim=1)
            correct += (predicted == labels.to(ctx.device)).sum().item()
    return correct / len(dataset)


def _environment(ctx: ddp.Context) -> dict:
    """The hardware and software behind the numbers, for the Setup section of docs/BENCHMARKS.md."""
    on_gpu = ctx.device.type == "cuda"
    return {
        "gpu": torch.cuda.get_device_name(ctx.device) if on_gpu else None,
        "gpus_on_machine": torch.cuda.device_count() if on_gpu else 0,
        "cpu_count": os.cpu_count(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "torch": torch.__version__,
        "cuda": torch.version.cuda if on_gpu else None,
        "nccl": ".".join(map(str, torch.cuda.nccl.version())) if ctx.backend == "nccl" else None,
    }


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """One command-line flag per TrainConfig field, e.g. --batch-size."""
    for field in fields(TrainConfig):
        kind = str if field.default is None else type(field.default)
        parser.add_argument("--" + field.name.replace("_", "-"), type=kind, default=field.default)


def config_from(args: argparse.Namespace, **changes) -> TrainConfig:
    values = {field.name: getattr(args, field.name) for field in fields(TrainConfig)}
    return TrainConfig(**{**values, **changes})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    add_arguments(parser)
    print(json.dumps(run(config_from(parser.parse_args())), indent=2))
