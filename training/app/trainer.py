"""Production CIFAR-10/ResNet-18 trainer with a small injectable callable boundary."""

import threading
from collections.abc import Callable
from pathlib import Path

from app.models import TrainingJob

MetricCallback = Callable[[int, dict[str, float]], None]


class TrainingCancelled(RuntimeError):
    pass


def train_cifar(
    job: TrainingJob,
    dataset_dir: Path,
    metric_callback: MetricCallback,
    stop_event: threading.Event,
) -> dict[str, float]:
    if job.model != "resnet18":
        raise ValueError(f"unsupported model {job.model!r}; Day 1 supports resnet18")
    if job.parallelism.strategy != "single":
        raise ValueError("DDP runtime integration is scheduled for Day 2; use strategy 'single'")

    import torch
    from distributed import ddp
    from distributed.train import TrainConfig, build_datasets, build_model
    from torch import nn

    torch.set_num_threads(job.resources.cpu_cores)
    seed = int(getattr(job.hyperparameters, "seed", 0))
    torch.manual_seed(seed)
    device = torch.device("cuda:0" if job.resources.gpu_count and torch.cuda.is_available() else "cpu")
    cifar_root = _cifar_root(dataset_dir)
    config = TrainConfig(
        model="resnet18",
        dataset="cifar10",
        data_dir=str(cifar_root),
        epochs=job.hyperparameters.epochs,
        batch_size=job.hyperparameters.batch_size,
        learning_rate=job.hyperparameters.learning_rate,
        num_workers=int(getattr(job.hyperparameters, "num_workers", 0)),
        device=str(device),
        seed=seed,
    )
    train_set, validation_set = build_datasets(config)
    context = ddp.Context(rank=0, world_size=1, device=device, backend=None)
    train_loader = ddp.make_loader(
        train_set,
        config.batch_size,
        context,
        shuffle=True,
        num_workers=config.num_workers,
        seed=seed,
    )
    validation_loader = torch.utils.data.DataLoader(
        validation_set, batch_size=config.batch_size, num_workers=config.num_workers
    )
    model = build_model("resnet18")
    model.conv1 = nn.Conv2d(3, 64, kernel_size=3, stride=1, padding=1, bias=False)
    model.maxpool = nn.Identity()
    model.to(device)
    optimizer = torch.optim.SGD(
        model.parameters(),
        lr=config.learning_rate,
        momentum=float(getattr(job.hyperparameters, "momentum", 0.9)),
    )
    loss_function = nn.CrossEntropyLoss()
    final: dict[str, float] = {}
    for epoch in range(config.epochs):
        ddp.set_epoch(train_loader, epoch)
        model.train()
        training_loss = 0.0
        seen = 0
        for images, labels in train_loader:
            if stop_event.is_set():
                raise TrainingCancelled("training stopped by cancellation or timeout")
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad(set_to_none=True)
            loss = loss_function(model(images), labels)
            loss.backward()
            optimizer.step()
            training_loss += loss.item() * labels.size(0)
            seen += labels.size(0)
        validation_loss, accuracy = _evaluate(model, validation_loader, loss_function, device, stop_event)
        final = {
            "train_loss": training_loss / seen,
            "validation_loss": validation_loss,
            "accuracy": accuracy,
        }
        metric_callback(epoch + 1, final)
    return final


def _cifar_root(dataset_dir: Path) -> Path:
    folders = [path for path in dataset_dir.rglob("cifar-10-batches-py") if path.is_dir()]
    if len(folders) != 1:
        raise ValueError("dataset archive must contain exactly one cifar-10-batches-py directory")
    return folders[0].parent


def _evaluate(model, loader, loss_function, device, stop_event) -> tuple[float, float]:
    import torch

    model.eval()
    total_loss = 0.0
    correct = total = 0
    with torch.no_grad():
        for images, labels in loader:
            if stop_event.is_set():
                raise TrainingCancelled("training stopped by cancellation or timeout")
            images, labels = images.to(device), labels.to(device)
            predictions = model(images)
            total_loss += loss_function(predictions, labels).item() * labels.size(0)
            correct += (predictions.argmax(dim=1) == labels).sum().item()
            total += labels.size(0)
    return total_loss / total, correct / total
