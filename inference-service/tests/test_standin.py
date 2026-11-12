"""The Inference stand-in: a prediction in the contract's shape, and 400 for a non-image."""

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from app.main import PNG_START, create_app

CONTRACT = Path(__file__).resolve().parents[2] / "contracts" / "openapi" / "inference-service.yaml"
USER = {"X-User-Id": "user-1"}


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
    assert client.get("/health").json() == {"status": "ok", "service": "inference-service"}


def test_predict(client, check):
    response = client.post("/predict", files={"file": ("cat.png", PNG_START + b"pixels")}, headers=USER)

    assert response.status_code == 200
    check(response.json(), "Prediction")


def test_not_an_image_is_400(client, check):
    response = client.post("/predict", files={"file": ("notes.txt", b"hello")}, headers=USER)

    assert response.status_code == 400
    check(response.json(), "Error")


def test_without_login_is_401(client):
    assert client.post("/predict", files={"file": ("cat.png", PNG_START)}).status_code == 401


def test_model_info(client, check):
    check(client.get("/model-info").json(), "ModelInfo")
