"""Test helpers.

Unit tests use a small in-memory SQLite database instead of PostgreSQL, and fake MLflow, Projects
and Inference services (an httpx transport that answers like they do), so they run in a second.
The real PostgreSQL + MLflow path is covered by `make up`, the contract tests and the e2e check.
"""

import json
import time
from pathlib import Path

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.db import SCHEMA, Base
from app.main import create_app

CONTRACT = Path(__file__).resolve().parents[2] / "contracts" / "openapi" / "model-registry.yaml"
ALICE = {"X-User-Id": "user-alice"}
BOB = {"X-User-Id": "user-bob"}


def registration(run_id: str = "run-a", **changes) -> dict:
    return {
        "project_id": "project-01",
        "name": "resnet18-cifar10",
        "mlflow_run_id": run_id,
        "job_id": "job-01",
        "dataset_id": "dataset-01",
        "dataset_version": 1,
    } | changes


class FakeServices:
    """MLflow, the Projects service and Inference, as far as the registry uses them."""

    def __init__(self) -> None:
        self.members = {("project-01", "user-alice"), ("project-02", "user-bob")}
        self.projects = {"project-01", "project-02"}
        self.runs: dict[str, dict] = {}
        self.logged_models: dict[str, dict] = {}
        self.registered: dict[str, list[dict]] = {}
        self.aliases: dict[str, str] = {}
        self.no_model: set[str] = set()  # runs that saved no model
        self.unhealthy: set[tuple[str, int]] = set()  # (model_id, version) Inference rejects
        self.candidates: list[tuple[str, dict]] = []
        self.switches: list[str] = []
        self.mlflow_down = False
        self.inference_down = False

    def add_run(self, run_id: str, status: str = "FINISHED", mlflow3: bool = True, tags: dict | None = None):
        outputs = {}
        if mlflow3:
            model_id = f"m-{run_id}"
            self.logged_models[model_id] = {
                "info": {
                    "model_id": model_id,
                    "artifact_uri": f"mlflow-artifacts:/1/models/{model_id}/artifacts",
                }
            }
            outputs = {"model_outputs": [{"model_id": model_id, "step": 0}]}
        self.runs[run_id] = {
            "info": {
                "run_id": run_id,
                "experiment_id": "1",
                "status": status,
                "artifact_uri": f"mlflow-artifacts:/1/{run_id}/artifacts",
            },
            "data": {
                "metrics": [{"key": "accuracy", "value": 0.91}, {"key": "loss", "value": float("nan")}],
                "tags": [{"key": k, "value": v} for k, v in (tags or {}).items()],
            },
            "outputs": outputs,
        }

    def handle(self, request: httpx.Request) -> httpx.Response:
        host, path = request.url.host, request.url.path
        if host == "mlflow":
            return self.mlflow(request, path.removeprefix("/api/2.0/mlflow"))
        if host == "project-service":
            project_id = path.rsplit("/", 1)[-1]
            if project_id not in self.projects:
                return httpx.Response(404, json={"error": {"code": "PROJECT_NOT_FOUND"}})
            member = (project_id, request.headers["X-User-Id"]) in self.members
            return httpx.Response(200 if member else 403, json={})
        if host == "inference-service":
            if self.inference_down:
                raise httpx.ConnectError("down")
            model_id = path.split("/")[3]
            if path.endswith("/refresh"):
                self.switches.append(model_id)
                return httpx.Response(200, json={})
            candidate = json.loads(request.content)
            self.candidates.append((model_id, candidate))
            if (model_id, candidate["version"]) in self.unhealthy:
                message = "the model output has the wrong shape"
                return httpx.Response(503, json={"error": {"code": "MODEL_UNHEALTHY", "message": message}})
            return httpx.Response(200, json={"status": "healthy"})
        raise AssertionError(f"unexpected call {request.method} {request.url}")

    def mlflow(self, request: httpx.Request, path: str) -> httpx.Response:
        if self.mlflow_down:
            raise httpx.ConnectError("down")
        missing = httpx.Response(404, json={"error_code": "RESOURCE_DOES_NOT_EXIST", "message": "missing"})
        body = json.loads(request.content) if request.content else {}
        if path == "/runs/get":
            run = self.runs.get(request.url.params["run_id"])
            # json.dumps writes NaN the way MLflow does; httpx's own json= refuses it
            return httpx.Response(200, content=json.dumps({"run": run})) if run else missing
        if path == "/logged-models/search":
            return httpx.Response(200, json={"models": []})
        if path.startswith("/logged-models/"):
            model = self.logged_models.get(path.rsplit("/", 1)[-1])
            return httpx.Response(200, json={"model": model}) if model else missing
        if path == "/artifacts/list":
            files = [] if request.url.params["run_id"] in self.no_model else [{"path": "model/MLmodel"}]
            return httpx.Response(200, json={"files": files})
        if path == "/registered-models/create":
            if body["name"] in self.registered:
                return httpx.Response(
                    400, json={"error_code": "RESOURCE_ALREADY_EXISTS", "message": "exists"}
                )
            self.registered[body["name"]] = []
            return httpx.Response(200, json={"registered_model": {"name": body["name"]}})
        if path == "/model-versions/create":
            versions = self.registered[body["name"]]
            versions.append(body)
            return httpx.Response(200, json={"model_version": {"version": str(len(versions))}})
        if path == "/registered-models/alias":
            self.aliases[body["name"]] = body["version"]
            return httpx.Response(200, json={})
        raise AssertionError(f"unexpected MLflow call {path}")


@pytest.fixture
def services() -> FakeServices:
    fake = FakeServices()
    for run_id in ("run-a", "run-b", "run-c"):
        fake.add_run(run_id)
    return fake


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    ).execution_options(schema_translate_map={SCHEMA: None})
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def client(engine, services, monkeypatch):
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
    monkeypatch.setenv("ARTIFACTS_BUCKET", "artifacts")
    with TestClient(create_app(engine, httpx.MockTransport(services.handle))) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def check():
    components = yaml.safe_load(CONTRACT.read_text())["components"]

    def matches(body, name):
        schema = {"$ref": f"#/components/schemas/{name}", "components": components}
        Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(body)

    return matches


@pytest.fixture
def dubai_time(monkeypatch):
    """The machine clock at UTC+4, as on a laptop in the UAE: naive times must still read as UTC."""
    monkeypatch.setenv("TZ", "Asia/Dubai")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()
