"""The Model Registry stand-in: register, promote, roll back, live version."""

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from app.main import create_app

CONTRACT = Path(__file__).resolve().parents[2] / "contracts" / "openapi" / "model-registry.yaml"
USER = {"X-User-Id": "user-1"}
RUN = {
    "project_id": "project-01",
    "name": "resnet18-cifar10",
    "mlflow_run_id": "abc123",
    "job_id": "job-01",
    "dataset_id": "dataset-01",
    "dataset_version": 1,
}


@pytest.fixture
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def check():
    components = yaml.safe_load(CONTRACT.read_text())["components"]

    def matches(body, name):
        schema = {"$ref": f"#/components/schemas/{name}", "components": components}
        Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(body)

    return matches


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "service": "model-registry"}


def test_register_promote_and_rollback(client, check):
    first = client.post("/models", json=RUN, headers=USER)
    second = client.post("/models", json={**RUN, "mlflow_run_id": "def456"}, headers=USER)
    model_id = first.json()["model_id"]

    assert first.status_code == second.status_code == 201
    check(first.json(), "ModelVersion")
    assert second.json()["version"] == 2
    assert client.get(f"/models/{model_id}/production").status_code == 404  # nothing live yet

    client.post(f"/models/{model_id}/versions/1/promote", headers=USER)
    live = client.post(f"/models/{model_id}/versions/2/promote", headers=USER).json()
    check(live, "Production")
    assert live["version"] == 2

    rolled_back = client.post(f"/models/{model_id}/rollback", headers=USER).json()
    assert rolled_back["version"] == 1
    assert client.get(f"/models/{model_id}/production").json()["version"] == 1
    check(client.get("/models", headers=USER).json(), "ModelList")
    check(client.get(f"/models/{model_id}/versions", headers=USER).json(), "ModelVersionList")


def test_rollback_with_nothing_before_is_409(client, check):
    model_id = client.post("/models", json=RUN, headers=USER).json()["model_id"]
    client.post(f"/models/{model_id}/versions/1/promote", headers=USER)

    response = client.post(f"/models/{model_id}/rollback", headers=USER)

    assert response.status_code == 409
    check(response.json(), "Error")


def test_unknown_model_is_404(client):
    assert client.get("/models/model-99/versions", headers=USER).status_code == 404
