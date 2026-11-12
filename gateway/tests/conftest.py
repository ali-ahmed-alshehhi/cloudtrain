"""Test helpers: fake services behind the gateway, so no real network is needed.

The fake services answer with an echo of what they received, so a test can check exactly
what the gateway forwarded. A service whose host name ends in "-down" refuses connections,
one ending in "-slow" never answers in time.
"""

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app

DEV_TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {DEV_TOKEN}"}
CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"

SERVICE_URLS = {
    "PROJECT_SERVICE_URL": "http://project-service:8001",
    "DATASET_SERVICE_URL": "http://dataset-service:8002",
    "JOB_SERVICE_URL": "http://job-service:8003",
    "MLFLOW_URL": "http://mlflow:5000",
    "MODEL_REGISTRY_URL": "http://model-registry:8006",
    "INFERENCE_SERVICE_URL": "http://inference-service:8007",
}


class NetworkBody(httpx.AsyncByteStream):
    """An answer body that arrives as a stream, like a real network answer."""

    def __init__(self, data: bytes) -> None:
        self.data = data

    async def __aiter__(self):
        yield self.data


def json_answer(status_code: int, body: dict) -> httpx.Response:
    data = json.dumps(body).encode()
    headers = {"content-type": "application/json", "content-length": str(len(data))}
    return httpx.Response(status_code, headers=headers, stream=NetworkBody(data))


class FakeServices:
    def __init__(self) -> None:
        self.received: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.received.append(request)
        host = request.url.host
        if host.endswith("-down"):
            raise httpx.ConnectError("connection refused", request=request)
        if host.endswith("-slow"):
            raise httpx.ReadTimeout("timed out", request=request)
        if host == "mlflow" and request.url.params.get("run_id") == "missing":
            body = {"error_code": "RESOURCE_DOES_NOT_EXIST", "message": "Run 'abc' not found"}
            return json_answer(404, body)
        echo = {
            "method": request.method,
            "url": str(request.url),
            "user_id": request.headers.get("x-user-id"),
            "request_id": request.headers.get("x-request-id"),
            "has_authorization": "authorization" in request.headers,
            "body_size": len(request.content),
        }
        return json_answer(200, echo)

    @property
    def last(self) -> httpx.Request:
        return self.received[-1]


@pytest.fixture
def local_env(monkeypatch):
    """The environment of a laptop running `make up`."""
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("DEV_AUTH_TOKEN", DEV_TOKEN)
    monkeypatch.setenv("DEV_USER_ID", "user-1")
    monkeypatch.delenv("DEPLOYED_PORTAL_URL", raising=False)
    for name, url in SERVICE_URLS.items():
        monkeypatch.setenv(name, url)
    return monkeypatch


@pytest.fixture
def services() -> FakeServices:
    return FakeServices()


@pytest.fixture
def client(local_env, services):
    """A gateway in front of the fake services."""
    with TestClient(create_app(transport=httpx.MockTransport(services.handle))) as test_client:
        yield test_client


@pytest.fixture
def error_schema() -> dict:
    return json.loads((CONTRACTS / "error-format.json").read_text())
