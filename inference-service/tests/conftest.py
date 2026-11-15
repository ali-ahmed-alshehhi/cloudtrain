"""Test helpers: real MLflow model folders on disk, and a fake Model Registry.

The models are real (a small CNN trained for a moment, and ResNet-18 as the training worker will
save it), loaded by the same code as in production; only the registry and the bucket are faked.
"""

from pathlib import Path

import httpx
import mlflow.pytorch
import numpy as np
import pytest
import torch
import torchvision
import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from mlflow.models import ModelSignature
from mlflow.types import Schema, TensorSpec

from app import fixture_model
from app.main import create_app

CONTRACT = Path(__file__).resolve().parents[2] / "contracts" / "openapi" / "inference-service.yaml"
USER = {"X-User-Id": "user-1"}


@pytest.fixture(scope="session")
def models(tmp_path_factory) -> dict[str, str]:
    """Model folders: the trained test CNN, ResNet-18 (both MLflow formats), and broken ones."""
    folder = tmp_path_factory.mktemp("models")
    paths = {name: str(folder / name) for name in ("tiny", "resnet18", "resnet18_pt2", "wrong_shape")}
    fixture_model.save(paths["tiny"])
    resnet = torchvision.models.resnet18(num_classes=10).eval()
    mlflow.pytorch.save_model(resnet, paths["resnet18"], serialization_format="pickle")
    signature = ModelSignature(
        inputs=Schema([TensorSpec(np.dtype("float32"), (-1, 3, 32, 32))]),
        outputs=Schema([TensorSpec(np.dtype("float32"), (-1, 10))]),
    )
    mlflow.pytorch.save_model(
        resnet,
        paths["resnet18_pt2"],
        serialization_format="pt2",
        signature=signature,
        input_example=np.zeros((1, 3, 32, 32), dtype=np.float32),
    )
    wrong = torch.nn.Sequential(torch.nn.Flatten(), torch.nn.Linear(3 * 32 * 32, 4))  # 4 scores, 10 labels
    mlflow.pytorch.save_model(wrong, paths["wrong_shape"], serialization_format="pickle")
    paths["missing"] = str(folder / "nothing-here")
    return paths


class FakeRegistry:
    def __init__(self) -> None:
        self.live: dict[str, dict] = {}
        self.known = {"model-01", "model-02"}
        self.down = False

    def promote(self, model_id: str, version: int, artifact_uri: str) -> None:
        self.live[model_id] = {
            "model_id": model_id,
            "name": "resnet18-cifar10",
            "version": version,
            "mlflow_run_id": f"run-{version}",
            "artifact_uri": artifact_uri,
            "promoted_at": "2026-11-20T10:00:00Z",
        }

    def handle(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("down")
        model_id = request.url.path.split("/")[2]
        if model_id not in self.known:
            return httpx.Response(404, json={"error": {"code": "MODEL_NOT_FOUND"}})
        if model_id not in self.live:
            return httpx.Response(404, json={"error": {"code": "NO_PRODUCTION_VERSION"}})
        return httpx.Response(200, json=self.live[model_id])


@pytest.fixture
def registry() -> FakeRegistry:
    return FakeRegistry()


@pytest.fixture
def client(registry, monkeypatch):
    monkeypatch.setenv("INFERENCE_REFRESH_SECONDS", "0")  # ask the registry on every request
    with TestClient(create_app(httpx.MockTransport(registry.handle))) as test_client:
        yield test_client


def candidate(version: int, artifact_uri: str) -> dict:
    return {
        "name": "resnet18-cifar10",
        "version": version,
        "mlflow_run_id": f"run-{version}",
        "artifact_uri": artifact_uri,
    }


@pytest.fixture(scope="session")
def check():
    components = yaml.safe_load(CONTRACT.read_text())["components"]

    def matches(body, name):
        schema = {"$ref": f"#/components/schemas/{name}", "components": components}
        Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(body)

    return matches
