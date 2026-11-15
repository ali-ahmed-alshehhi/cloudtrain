"""Load a model saved in MLflow's PyTorch format, check it, and turn an image into a prediction.

Any model logged with `mlflow.pytorch.log_model` works, in either of MLflow's formats ("pickle", or
"pt2" with a batch of one). The model takes a (1, 3, size, size) image and returns one score per
class. How to prepare the image is read from the model's MLflow metadata, with CIFAR-10 defaults
(the first use case, ResNet-18 on CIFAR-10):

    mlflow.pytorch.log_model(model, name="model", metadata={
        "labels": ["airplane", ...],          # one per output, in order
        "image_size": 32,                     # images are resized to image_size x image_size
        "normalize_mean": [0.4914, 0.4822, 0.4465],
        "normalize_std": [0.2470, 0.2435, 0.2616],
    })
"""

import io
import math
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import mlflow.pytorch
import numpy as np
import torch
from mlflow.models import Model as MlflowModel
from PIL import Image, UnidentifiedImageError

from app.common import now_utc

CIFAR10_LABELS = ["airplane", "automobile", "bird", "cat", "deer", "dog", "frog", "horse", "ship", "truck"]
CIFAR10_MEAN = [0.4914, 0.4822, 0.4465]
CIFAR10_STD = [0.2470, 0.2435, 0.2616]
PNG_START = b"\x89PNG\r\n\x1a\n"
JPEG_START = b"\xff\xd8\xff"


class InvalidImage(Exception):
    """The upload is not a PNG or JPEG image we can read."""


class ModelProblem(Exception):
    """The model could not be loaded, or it failed its health check."""


@dataclass(frozen=True)
class Deployment:
    """Which version to serve, as the Model Registry describes it."""

    model_id: str
    name: str
    version: int
    mlflow_run_id: str
    artifact_uri: str

    def same_as(self, other: "Deployment") -> bool:
        return (self.version, self.artifact_uri) == (other.version, other.artifact_uri)


@dataclass
class LoadedModel:
    deployment: Deployment
    network: torch.nn.Module
    labels: list[str]
    image_size: int
    mean: torch.Tensor
    std: torch.Tensor
    loaded_at: datetime = field(default_factory=now_utc)

    def scores(self, pixels: torch.Tensor) -> torch.Tensor:
        """Class probabilities for a (1, 3, size, size) tensor of pixels between 0 and 1."""
        with torch.no_grad():
            output = self.network((pixels - self.mean) / self.std)
        if not isinstance(output, torch.Tensor) or tuple(output.shape) != (1, len(self.labels)):
            shape = tuple(output.shape) if isinstance(output, torch.Tensor) else type(output).__name__
            raise ModelProblem(f"the model answered {shape}, expected (1, {len(self.labels)}) scores")
        probabilities = torch.softmax(output.float(), dim=1)[0]
        if not torch.isfinite(probabilities).all():
            raise ModelProblem("the model answered scores that are not numbers")
        return probabilities

    def predict(self, image: bytes, top_k: int) -> list[dict]:
        probabilities = self.scores(read_image(image, self.image_size))
        best = torch.topk(probabilities, k=min(top_k, len(self.labels)))
        return [
            {"label": self.labels[index], "score": round(min(max(score, 0.0), 1.0), 6)}
            for score, index in zip(best.values.tolist(), best.indices.tolist(), strict=True)
        ]

    def check(self) -> None:
        """The health check: one prediction on a fixed test image must give one valid score per class."""
        test_image = torch.linspace(0, 1, 3 * self.image_size**2).reshape(
            1, 3, self.image_size, self.image_size
        )
        try:
            probabilities = self.scores(test_image)
        except ModelProblem:
            raise
        except Exception as error:
            raise ModelProblem(f"the model failed on a test image: {error}") from None
        if not math.isclose(float(probabilities.sum()), 1.0, abs_tol=1e-3):
            raise ModelProblem("the model's scores do not add up")


def read_image(data: bytes, size: int) -> torch.Tensor:
    """PNG or JPEG bytes -> a (1, 3, size, size) tensor of pixels between 0 and 1."""
    if not data.startswith((PNG_START, JPEG_START)):
        raise InvalidImage("Send a PNG or JPEG image")
    try:
        with Image.open(io.BytesIO(data)) as image:
            image = image.convert("RGB").resize((size, size), Image.Resampling.BILINEAR)
            pixels = np.asarray(image, dtype=np.float32) / 255.0
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise InvalidImage("The image could not be read (broken or too large)") from None
    return torch.from_numpy(pixels).permute(2, 0, 1).unsqueeze(0).contiguous()


def fetch_files(artifact_uri: str, folder: Path, s3_client: Callable) -> Path:
    """Copy the model's files to `folder`. Accepts s3://bucket/prefix, file:// and plain paths."""
    parts = urlsplit(artifact_uri)
    if parts.scheme == "s3":
        bucket, prefix = parts.netloc, parts.path.strip("/") + "/"
        s3 = s3_client()
        count = 0
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
            for item in page.get("Contents", []):
                target = folder / item["Key"][len(prefix) :]
                target.parent.mkdir(parents=True, exist_ok=True)
                s3.download_file(bucket, item["Key"], str(target))
                count += 1
        if count == 0:
            raise ModelProblem(f"no model files at {artifact_uri}")
        return folder
    if parts.scheme in ("", "file"):
        local = Path(parts.path if parts.scheme == "file" else artifact_uri)
        if not (local / "MLmodel").is_file():
            raise ModelProblem(f"no MLflow model at {artifact_uri}")
        return local
    raise ModelProblem(f"cannot read model files from {artifact_uri} (use s3:// or a local path)")


def _floats(values, name: str) -> torch.Tensor:
    if not (
        isinstance(values, list) and len(values) == 3 and all(isinstance(v, int | float) for v in values)
    ):
        raise ModelProblem(f"metadata {name} must be 3 numbers")
    if name == "normalize_std" and min(values) <= 0:
        raise ModelProblem("metadata normalize_std must be above 0")
    return torch.tensor(values, dtype=torch.float32).reshape(1, 3, 1, 1)


def load(deployment: Deployment, s3_client: Callable) -> LoadedModel:
    """Download, load and health-check one model version. Raises ModelProblem."""
    folder = Path(tempfile.mkdtemp(prefix=f"{deployment.model_id}-v{deployment.version}-"))
    try:
        local = fetch_files(deployment.artifact_uri, folder, s3_client)
        try:
            metadata = MlflowModel.load(str(local)).metadata or {}
            network = mlflow.pytorch.load_model(str(local), map_location="cpu")
        except Exception as error:
            raise ModelProblem(f"not a loadable MLflow PyTorch model: {error}") from None
        labels = metadata.get("labels", CIFAR10_LABELS)
        image_size = metadata.get("image_size", 32)
        if not (isinstance(labels, list) and labels and all(isinstance(label, str) for label in labels)):
            raise ModelProblem("metadata labels must be a list of names")
        if not (isinstance(image_size, int) and 8 <= image_size <= 1024):
            raise ModelProblem("metadata image_size must be a whole number from 8 to 1024")
        try:
            network.eval()
        except NotImplementedError:
            pass  # a "pt2" model is exported already in evaluation mode and refuses eval()
        loaded = LoadedModel(
            deployment=deployment,
            network=network,
            labels=labels,
            image_size=image_size,
            mean=_floats(metadata.get("normalize_mean", CIFAR10_MEAN), "normalize_mean"),
            std=_floats(metadata.get("normalize_std", CIFAR10_STD), "normalize_std"),
        )
        loaded.check()
        return loaded
    finally:
        shutil.rmtree(folder, ignore_errors=True)  # the model is in memory now
