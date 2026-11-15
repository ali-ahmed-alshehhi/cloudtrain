"""A small REAL test model, until the training worker logs the first ResNet-18 (Abdullah, Fri 20 Nov).

It is a three-layer CNN (the worker's "tiny" model) trained for a few seconds on CPU on synthetic
32x32 images: every CIFAR-10 class is a fixed random pattern under noise, so the model really
learns to tell the classes apart, and `class_image(label)` makes a PNG it classifies correctly.
It is saved in exactly the format the worker uses (MLflow PyTorch model in an MLflow run, with the
job and dataset tags), so the registry and inference treat it like a real training result.

Log one to MLflow and print its run ID (inside the Docker network, where MLflow is reachable):
    docker compose exec inference-service python -m app.fixture_model --job-id job-01 \\
        --project-id project-01 --dataset-id dataset-01 --dataset-version 1
"""

import argparse
import io

import mlflow.pytorch  # also makes `mlflow` itself available
import numpy as np
import torch
from PIL import Image
from torch import nn

from app.model import CIFAR10_LABELS

IMAGE_SIZE = 32
MEAN, STD = [0.5, 0.5, 0.5], [0.25, 0.25, 0.25]
METADATA = {"labels": CIFAR10_LABELS, "image_size": IMAGE_SIZE, "normalize_mean": MEAN, "normalize_std": STD}


def patterns() -> torch.Tensor:
    """One fixed pattern per class (normalised units), the same every time."""
    return torch.randn(
        len(CIFAR10_LABELS), 3, IMAGE_SIZE, IMAGE_SIZE, generator=torch.Generator().manual_seed(0)
    )


def build() -> nn.Module:
    return nn.Sequential(
        nn.Conv2d(3, 16, 3, stride=2, padding=1),
        nn.ReLU(),
        nn.Conv2d(16, 32, 3, stride=2, padding=1),
        nn.ReLU(),
        nn.Flatten(),
        nn.Linear(32 * 8 * 8, len(CIFAR10_LABELS)),
    )


def batch(size: int, generator: torch.Generator) -> tuple[torch.Tensor, torch.Tensor]:
    labels = torch.randint(0, len(CIFAR10_LABELS), (size,), generator=generator)
    noise = 0.5 * torch.randn(size, 3, IMAGE_SIZE, IMAGE_SIZE, generator=generator)
    return (0.5 * patterns()[labels] + noise).clamp(-2, 2), labels


def train(steps: int = 150, seed: int = 0) -> tuple[nn.Module, dict]:
    """Train on CPU (a few seconds) and return the model and its metrics."""
    torch.manual_seed(seed)
    generator = torch.Generator().manual_seed(seed)
    model = build()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.003)
    loss_fn = nn.CrossEntropyLoss()
    model.train()
    for _ in range(steps):
        images, labels = batch(64, generator)
        optimizer.zero_grad()
        loss = loss_fn(model(images), labels)
        loss.backward()
        optimizer.step()
    model.eval()
    images, labels = batch(500, torch.Generator().manual_seed(seed + 1))
    with torch.no_grad():
        accuracy = (model(images).argmax(dim=1) == labels).float().mean().item()
    return model, {"accuracy": accuracy, "loss": loss.item()}


def class_image(label: str) -> bytes:
    """A PNG of one class's pattern, in pixels (what a user would upload)."""
    normalised = 0.5 * patterns()[CIFAR10_LABELS.index(label)]
    pixels = (normalised * torch.tensor(STD).reshape(3, 1, 1) + torch.tensor(MEAN).reshape(3, 1, 1)).clamp(
        0, 1
    )
    array = (pixels.permute(1, 2, 0).numpy() * 255).round().astype(np.uint8)
    output = io.BytesIO()
    Image.fromarray(array).save(output, format="PNG")
    return output.getvalue()


def save(path: str, steps: int = 150) -> dict:
    """Train and save as an MLflow model folder (for the unit tests). Returns the metrics."""
    model, metrics = train(steps)
    mlflow.pytorch.save_model(model, path, serialization_format="pickle", metadata=METADATA)
    return metrics


def broken() -> nn.Module:
    """A model that loads but answers 4 scores for 10 labels: it must fail the health check."""
    return nn.Sequential(nn.Flatten(), nn.Linear(3 * IMAGE_SIZE * IMAGE_SIZE, 4))


def log_run(tags: dict, steps: int = 150, faulty: bool = False) -> str:
    """Train, log an MLflow run with the model (as the training worker does) and return its run ID."""
    mlflow.set_experiment("cloudtrain-test-models")
    with mlflow.start_run(tags=tags) as run:
        model, metrics = (broken(), {"accuracy": 0.0}) if faulty else train(steps)
        mlflow.log_params({"model": "tiny", "steps": steps, "dataset": "synthetic"})
        mlflow.log_metrics(metrics)
        mlflow.pytorch.log_model(model, name="model", serialization_format="pickle", metadata=METADATA)
    return run.info.run_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--steps", type=int, default=150)
    parser.add_argument("--broken", action="store_true", help="log a model that fails the health check")
    args = parser.parse_args()
    run_tags = {
        "project_id": args.project_id,
        "job_id": args.job_id,
        "dataset_id": args.dataset_id,
        "dataset_version": args.dataset_version,
    }
    print(log_run(run_tags, args.steps, faulty=args.broken))
