"""Load a CloudTrain model bundle and print a prediction for one sample.

Usage:
  python -m scripts.evaluate_bundle --bundle /path/to/model-bundle.pt
  python -m scripts.evaluate_bundle --bundle /path/to/model-bundle.pt --csv /path/to/row.csv
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import torch


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--csv", type=Path, help="optional one-row or multi-row CSV for tabular_mlp")
    args = parser.parse_args()
    payload = torch.load(args.bundle, map_location="cpu", weights_only=False)
    model_type = payload.get("model_type")
    if model_type == "tabular_mlp":
        from app.tabular import TabularMLP

        model = TabularMLP(**payload["architecture"])
        model.load_state_dict(payload["model_state_dict"])
        model.eval()
        features = payload["preprocessing"]["feature_names"]
        mean = torch.tensor(payload["preprocessing"]["feature_mean"], dtype=torch.float32)
        scale = torch.tensor(payload["preprocessing"]["feature_scale"], dtype=torch.float32)
        if args.csv:
            with args.csv.open(newline="", encoding="utf-8-sig") as source:
                row = next(csv.DictReader(source))
            values = torch.tensor([float(row[name]) for name in features], dtype=torch.float32)
        else:
            values = mean
        inputs = ((values - mean) / scale).unsqueeze(0)
        with torch.no_grad():
            probabilities = torch.softmax(model(inputs), dim=1)[0]
        labels = payload["class_labels"]
        prediction = {
            "model_type": model_type,
            "predicted_label": labels[int(probabilities.argmax().item())],
            "probabilities": {label: float(probabilities[index]) for index, label in enumerate(labels)},
        }
    elif model_type == "resnet18":
        from distributed.train import build_model
        from torch import nn

        model = build_model("resnet18")
        model.conv1 = nn.Conv2d(3, 64, kernel_size=3, stride=1, padding=1, bias=False)
        model.maxpool = nn.Identity()
        model.load_state_dict(payload["model_state_dict"])
        model.eval()
        image = torch.zeros(1, 3, 32, 32)
        with torch.no_grad():
            probabilities = torch.softmax(model(image), dim=1)[0]
        prediction = {
            "model_type": model_type,
            "predicted_class": int(probabilities.argmax().item()),
            "probabilities": probabilities.tolist(),
        }
    else:
        raise SystemExit(f"unsupported model bundle type: {model_type!r}")
    print(json.dumps(prediction, indent=2))


if __name__ == "__main__":
    main()
