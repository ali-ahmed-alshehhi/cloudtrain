"""Reproducible CIFAR-10 and tabular training, including rank-safe DDP."""

import io
import json
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.artifacts import CHECKPOINT_SCHEMA_VERSION, store_from_environment
from app.models import TrainingJob

MetricCallback = Callable[[int, dict[str, float]], None]


@dataclass
class TrainingOutcome:
    metrics: dict[str, float]
    model: Any
    input_example: Any
    model_bundle: bytes
    artifact_uri: str | None = None


class TrainingCancelled(RuntimeError):
    pass


def train_cifar(
    job: TrainingJob,
    dataset_dir: Path,
    metric_callback: MetricCallback,
    stop_event: threading.Event,
    *,
    artifact_store=None,
) -> TrainingOutcome:
    if job.model not in {"resnet18", "tabular_mlp"}:
        raise ValueError(f"unsupported model {job.model!r}; use resnet18 or tabular_mlp")
    store = artifact_store or store_from_environment()
    checksum = _dataset_checksum(dataset_dir)
    compatibility = _compatibility(job, checksum)
    resume = store.load_latest(job.job_id, compatibility)
    if stop_event.is_set():
        raise TrainingCancelled("training stopped by cancellation or timeout")

    if job.parallelism.strategy == "ddp":
        outcome, epoch_records = _run_ddp(job, dataset_dir, compatibility, resume, stop_event)
        if stop_event.is_set():
            raise TrainingCancelled("training stopped by cancellation or timeout")
        for record in epoch_records:
            metric_callback(record["epoch"], record["metrics"])
            store.save_checkpoint(
                job.job_id,
                record["epoch"],
                record["checkpoint"],
                compatibility,
                is_best=record["is_best"],
            )
    else:
        import torch
        from distributed import ddp

        device = torch.device("cuda:0" if job.resources.gpu_count and torch.cuda.is_available() else "cpu")
        context = ddp.Context(rank=0, world_size=1, device=device, backend=None)

        def publish(epoch, metrics, checkpoint, is_best):
            metric_callback(epoch, metrics)
            store.save_checkpoint(job.job_id, epoch, checkpoint, compatibility, is_best=is_best)

        outcome, _ = _train_context(context, job, dataset_dir, resume, publish, stop_event.is_set)

    outcome.artifact_uri = store.save_final(job.job_id, outcome.model_bundle, compatibility)
    return outcome


def _run_ddp(job, dataset_dir, compatibility, resume, stop_event):
    import torch
    from distributed import ddp

    with tempfile.TemporaryDirectory(prefix="cloudtrain-ddp-") as folder:
        root = Path(folder)
        (root / "job.json").write_text(job.model_dump_json())
        (root / "compatibility.json").write_text(json.dumps(compatibility, sort_keys=True))
        if resume:
            (root / "resume.pt").write_bytes(resume)
        watcher_done = threading.Event()

        def forward_cancellation():
            while not watcher_done.is_set():
                if stop_event.wait(0.05):
                    (root / "CANCELLED").touch()
                    return

        watcher = threading.Thread(target=forward_cancellation, daemon=True)
        watcher.start()
        try:
            ddp.launch(
                _ddp_entry,
                job.parallelism.world_size,
                args=(str(dataset_dir), str(root)),
                device="auto",
            )
        finally:
            watcher_done.set()
            watcher.join(timeout=0.2)
        summary = torch.load(root / "outcome.pt", map_location="cpu", weights_only=False)
        epoch_records = []
        for checkpoint_path in sorted(root.glob("record-*.pt")):
            record = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
            epoch_records.append(record)
        model, example = _restore_model_for_tracking(job, summary)
        return (
            TrainingOutcome(summary["metrics"], model, example, summary["model_bundle"]),
            epoch_records,
        )


def _ddp_entry(ctx, dataset_dir: str, output_dir: str) -> None:
    """Module-level spawn target; only rank zero emits checkpoints and results."""
    from distributed import ddp

    job = TrainingJob.model_validate_json(Path(output_dir, "job.json").read_text())
    resume_path = Path(output_dir, "resume.pt")
    resume = resume_path.read_bytes() if resume_path.exists() else None

    def publish(epoch, metrics, checkpoint, is_best):
        if ctx.is_main:
            import torch

            torch.save(
                {
                    "epoch": epoch,
                    "metrics": metrics,
                    "is_best": is_best,
                    "checkpoint": checkpoint,
                },
                Path(output_dir, f"record-{epoch:06d}.pt"),
            )

    outcome, _ = _train_context(
        ctx,
        job,
        Path(dataset_dir),
        resume,
        publish,
        lambda: Path(output_dir, "CANCELLED").exists(),
    )
    if ctx.is_main:
        import torch

        torch.save(
            {
                "metrics": outcome.metrics,
                "model_bundle": outcome.model_bundle,
                "input_example": outcome.input_example,
            },
            Path(output_dir, "outcome.pt"),
        )
    if ctx.distributed:
        ddp.dist.barrier()


def _train_context(ctx, job, dataset_dir: Path, resume: bytes | None, publish, cancel_check):
    import torch
    from distributed import ddp
    from torch import nn
    from torch.utils.data import DataLoader, TensorDataset

    from app.reproducibility import seed_everything, seed_worker
    from app.tabular import (
        DEFAULT_TARGET_COLUMN,
        TabularMLP,
        find_csv,
        load_tabular_data,
        make_model_bundle,
    )

    seed = int(getattr(job.hyperparameters, "seed", 0))
    seed_everything(seed)
    torch.set_num_threads(max(1, job.resources.cpu_cores // ctx.world_size))
    target_column = str(getattr(job.hyperparameters, "target_column", DEFAULT_TARGET_COLUMN))
    hidden_size = int(getattr(job.hyperparameters, "hidden_size", 32))
    tabular_data = None
    if job.model == "tabular_mlp":
        tabular_data = load_tabular_data(
            find_csv(dataset_dir),
            target_column=target_column,
            seed=seed,
            validation_fraction=float(getattr(job.hyperparameters, "validation_fraction", 0.2)),
        )
        train_set = TensorDataset(tabular_data.train_inputs, tabular_data.train_targets)
        validation_set = TensorDataset(tabular_data.validation_inputs, tabular_data.validation_targets)
        plain_model = TabularMLP(
            len(tabular_data.feature_names),
            len(tabular_data.class_labels),
            hidden_size,
        ).to(ctx.device)
    else:
        from distributed.train import TrainConfig, build_datasets, build_model

        config = TrainConfig(
            model="resnet18",
            dataset="cifar10",
            data_dir=str(_cifar_root(dataset_dir)),
            epochs=job.hyperparameters.epochs,
            batch_size=job.hyperparameters.batch_size,
            learning_rate=job.hyperparameters.learning_rate,
            num_workers=int(getattr(job.hyperparameters, "num_workers", 0)),
            device=str(ctx.device),
            seed=seed,
        )
        train_set, validation_set = build_datasets(config)
        plain_model = build_model("resnet18")
        plain_model.conv1 = nn.Conv2d(3, 64, kernel_size=3, stride=1, padding=1, bias=False)
        plain_model.maxpool = nn.Identity()
        plain_model.to(ctx.device)

    optimizer = torch.optim.SGD(
        plain_model.parameters(),
        lr=job.hyperparameters.learning_rate,
        momentum=float(getattr(job.hyperparameters, "momentum", 0.9)),
    )
    start_epoch = 0
    best_loss = float("inf")
    if resume:
        state = torch.load(io.BytesIO(resume), map_location=ctx.device, weights_only=False)
        plain_model.load_state_dict(state["model_state_dict"])
        optimizer.load_state_dict(state["optimizer_state_dict"])
        start_epoch = int(state["epoch"])
        best_loss = float(state["best_validation_loss"])

    model = ddp.wrap(plain_model, ctx)
    workers = int(getattr(job.hyperparameters, "num_workers", 0))
    train_loader = ddp.make_loader(
        train_set,
        job.hyperparameters.batch_size,
        ctx,
        shuffle=True,
        num_workers=workers,
        seed=seed,
    )
    train_loader.worker_init_fn = seed_worker
    validation_loader = DataLoader(
        validation_set,
        batch_size=job.hyperparameters.batch_size,
        shuffle=False,
        generator=torch.Generator().manual_seed(seed),
        worker_init_fn=seed_worker,
        num_workers=workers,
        multiprocessing_context=ddp.worker_context(workers),
    )
    loss_function = nn.CrossEntropyLoss()
    final: dict[str, float] = {}
    for epoch in range(start_epoch, job.hyperparameters.epochs):
        if cancel_check():
            raise TrainingCancelled("training stopped by cancellation or timeout")
        ddp.set_epoch(train_loader, epoch)
        model.train()
        training_loss = 0.0
        seen = 0
        for inputs, labels in train_loader:
            if cancel_check():
                raise TrainingCancelled("training stopped by cancellation or timeout")
            inputs, labels = inputs.to(ctx.device), labels.to(ctx.device)
            optimizer.zero_grad(set_to_none=True)
            loss = loss_function(model(inputs), labels)
            loss.backward()
            optimizer.step()
            training_loss += loss.item() * labels.size(0)
            seen += labels.size(0)
        totals = torch.tensor([training_loss, seen], dtype=torch.float64, device=ctx.device)
        if ctx.distributed:
            ddp.dist.all_reduce(totals)
        if ctx.is_main:
            validation_loss, accuracy, f1 = _evaluate(
                ddp.unwrap(model), validation_loader, loss_function, ctx.device
            )
            values = torch.tensor(
                [validation_loss, accuracy, f1],
                dtype=torch.float64,
                device=ctx.device,
            )
        else:
            values = torch.zeros(3, dtype=torch.float64, device=ctx.device)
        if ctx.distributed:
            ddp.dist.broadcast(values, src=0)
        final = {
            "train_loss": float(totals[0].item() / totals[1].item()),
            "validation_loss": float(values[0].item()),
            "accuracy": float(values[1].item()),
            "f1": float(values[2].item()),
        }
        is_best = final["validation_loss"] < best_loss
        best_loss = min(best_loss, final["validation_loss"])
        if ctx.is_main:
            checkpoint = _checkpoint_bytes(ddp.unwrap(model), optimizer, epoch + 1, best_loss)
            publish(epoch + 1, final, checkpoint, is_best)

    if not ctx.is_main:
        return TrainingOutcome(final, None, None, b""), []
    plain_model = ddp.unwrap(model)
    if tabular_data:
        bundle = make_model_bundle(
            plain_model,
            tabular_data,
            target_column=target_column,
            hidden_size=hidden_size,
        )
        example = tabular_data.validation_inputs[: min(5, len(validation_set))].numpy()
    else:
        bundle = _cifar_bundle(plain_model)
        example = torch.zeros(1, 3, 32, 32).numpy()
    return TrainingOutcome(final, plain_model.cpu(), example, bundle), []


def _checkpoint_bytes(model, optimizer, epoch: int, best_loss: float) -> bytes:
    import torch

    buffer = io.BytesIO()
    torch.save(
        {
            "schema_version": CHECKPOINT_SCHEMA_VERSION,
            "epoch": epoch,
            "best_validation_loss": best_loss,
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
        },
        buffer,
    )
    return buffer.getvalue()


def _cifar_bundle(model) -> bytes:
    import torch

    buffer = io.BytesIO()
    torch.save(
        {
            "format_version": 1,
            "model_type": "resnet18",
            "input_schema": {"shape": [None, 3, 32, 32], "dtype": "float32"},
            "normalization": {
                "mean": [0.4914, 0.4822, 0.4465],
                "std": [0.2470, 0.2435, 0.2616],
            },
            "class_labels": list(range(10)),
            "model_state_dict": model.state_dict(),
        },
        buffer,
    )
    return buffer.getvalue()


def _restore_model_for_tracking(job, summary):
    import torch

    if job.model == "tabular_mlp":
        from app.tabular import load_model_bundle

        model, _ = load_model_bundle(summary["model_bundle"])
        return model, summary["input_example"]
    from distributed.train import build_model
    from torch import nn

    bundle = torch.load(io.BytesIO(summary["model_bundle"]), map_location="cpu", weights_only=False)
    model = build_model("resnet18")
    model.conv1 = nn.Conv2d(3, 64, kernel_size=3, stride=1, padding=1, bias=False)
    model.maxpool = nn.Identity()
    model.load_state_dict(bundle["model_state_dict"])
    model.eval()
    return model, summary["input_example"]


def _dataset_checksum(dataset_dir: Path) -> str:
    marker = dataset_dir / ".cloudtrain-checksum-sha256"
    if marker.exists():
        return marker.read_text().strip()
    import hashlib

    digest = hashlib.sha256()
    for path in sorted(item for item in dataset_dir.rglob("*") if item.is_file()):
        if path.name.startswith(".cloudtrain-"):
            continue
        digest.update(path.relative_to(dataset_dir).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _compatibility(job: TrainingJob, checksum: str) -> dict[str, Any]:
    return {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "job_id": job.job_id,
        "model": job.model,
        "dataset_checksum": checksum,
        "hyperparameters": job.hyperparameters.model_dump(),
        "strategy": job.parallelism.strategy,
        "world_size": job.parallelism.world_size,
    }


def _cifar_root(dataset_dir: Path) -> Path:
    folders = [path for path in dataset_dir.rglob("cifar-10-batches-py") if path.is_dir()]
    if len(folders) != 1:
        raise ValueError("dataset archive must contain exactly one cifar-10-batches-py directory")
    return folders[0].parent


def _evaluate(model, loader, loss_function, device) -> tuple[float, float, float]:
    import torch

    model.eval()
    total_loss = 0.0
    correct = total = 0
    predictions_seen: list[int] = []
    labels_seen: list[int] = []
    with torch.no_grad():
        for inputs, labels in loader:
            inputs, labels = inputs.to(device), labels.to(device)
            predictions = model(inputs)
            total_loss += loss_function(predictions, labels).item() * labels.size(0)
            predicted = predictions.argmax(dim=1)
            correct += (predicted == labels).sum().item()
            total += labels.size(0)
            predictions_seen.extend(predicted.cpu().tolist())
            labels_seen.extend(labels.cpu().tolist())
    return total_loss / total, correct / total, _macro_f1(predictions_seen, labels_seen)


def _macro_f1(predictions: list[int], labels: list[int]) -> float:
    scores = []
    for label in sorted(set(labels)):
        pairs = list(zip(predictions, labels, strict=True))
        true_positive = sum(p == label and y == label for p, y in pairs)
        false_positive = sum(p == label and y != label for p, y in pairs)
        false_negative = sum(p != label and y == label for p, y in pairs)
        denominator = 2 * true_positive + false_positive + false_negative
        scores.append(0.0 if denominator == 0 else 2 * true_positive / denominator)
    return sum(scores) / len(scores)
