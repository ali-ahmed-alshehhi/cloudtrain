"""Wisconsin-style numeric CSV preparation and loadable MLP bundles."""

import csv
import io
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from torch import nn

DEFAULT_TARGET_COLUMN = "diagnosis"


@dataclass(frozen=True)
class TabularData:
    train_inputs: torch.Tensor
    train_targets: torch.Tensor
    validation_inputs: torch.Tensor
    validation_targets: torch.Tensor
    feature_names: list[str]
    class_labels: list[str]
    feature_mean: np.ndarray
    feature_scale: np.ndarray


class TabularMLP(nn.Module):
    def __init__(self, input_features: int, classes: int, hidden_size: int = 32) -> None:
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(input_features, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, classes),
        )

    def forward(self, inputs):
        return self.network(inputs)


def find_csv(dataset_dir: Path) -> Path:
    files = sorted(dataset_dir.rglob("*.csv"))
    if len(files) != 1:
        raise ValueError("tabular_mlp dataset archive must contain exactly one CSV file")
    return files[0]


def load_tabular_data(
    csv_path: Path,
    *,
    target_column: str = DEFAULT_TARGET_COLUMN,
    seed: int,
    validation_fraction: float = 0.2,
) -> TabularData:
    if not 0 < validation_fraction < 1:
        raise ValueError("validation_fraction must be between 0 and 1")
    with csv_path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames or target_column not in reader.fieldnames:
            raise ValueError(f"CSV is missing target column {target_column!r}")
        features = [name for name in reader.fieldnames if name != target_column]
        if not features:
            raise ValueError("CSV needs at least one numeric feature column")
        rows = list(reader)
    if not rows:
        raise ValueError("CSV contains no data rows")
    try:
        inputs = np.asarray([[float(row[name]) for name in features] for row in rows], dtype=np.float32)
    except (TypeError, ValueError) as error:
        raise ValueError("all tabular feature values must be numeric and non-empty") from error
    if not np.isfinite(inputs).all():
        raise ValueError("all tabular feature values must be finite")

    labels = [row[target_column] for row in rows]
    class_labels = sorted(set(labels))
    if len(class_labels) < 2:
        raise ValueError("target column needs at least two classes")
    class_index = {label: index for index, label in enumerate(class_labels)}
    targets = np.asarray([class_index[label] for label in labels], dtype=np.int64)
    train_indices, validation_indices = _stratified_indices(targets, seed, validation_fraction)
    mean = inputs[train_indices].mean(axis=0)
    scale = inputs[train_indices].std(axis=0)
    scale[scale == 0] = 1
    standardized = (inputs - mean) / scale
    return TabularData(
        train_inputs=torch.from_numpy(standardized[train_indices]),
        train_targets=torch.from_numpy(targets[train_indices]),
        validation_inputs=torch.from_numpy(standardized[validation_indices]),
        validation_targets=torch.from_numpy(targets[validation_indices]),
        feature_names=features,
        class_labels=class_labels,
        feature_mean=mean,
        feature_scale=scale,
    )


def _stratified_indices(
    targets: np.ndarray, seed: int, validation_fraction: float
) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    train: list[int] = []
    validation: list[int] = []
    for label in np.unique(targets):
        indices = np.flatnonzero(targets == label)
        if len(indices) < 2:
            raise ValueError("each target class needs at least two rows for a stratified split")
        indices = rng.permutation(indices)
        count = min(len(indices) - 1, max(1, round(len(indices) * validation_fraction)))
        validation.extend(indices[:count].tolist())
        train.extend(indices[count:].tolist())
    return rng.permutation(train), rng.permutation(validation)


def make_model_bundle(
    model: nn.Module,
    data: TabularData,
    *,
    target_column: str,
    hidden_size: int = 32,
) -> bytes:
    buffer = io.BytesIO()
    torch.save(
        {
            "format_version": 1,
            "model_type": "tabular_mlp",
            "model_state_dict": model.state_dict(),
            "architecture": {
                "input_features": len(data.feature_names),
                "classes": len(data.class_labels),
                "hidden_size": hidden_size,
            },
            "preprocessing": {
                "feature_names": data.feature_names,
                "feature_mean": data.feature_mean.tolist(),
                "feature_scale": data.feature_scale.tolist(),
                "target_column": target_column,
            },
            "class_labels": data.class_labels,
            "input_schema": {name: "float32" for name in data.feature_names},
        },
        buffer,
    )
    return buffer.getvalue()


def load_model_bundle(payload: bytes) -> tuple[TabularMLP, dict]:
    bundle = torch.load(io.BytesIO(payload), map_location="cpu", weights_only=False)
    model = TabularMLP(**bundle["architecture"])
    model.load_state_dict(bundle["model_state_dict"])
    model.eval()
    return model, bundle
