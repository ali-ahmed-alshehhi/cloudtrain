"""The MLflow route through the gateway, against the real MLflow container (task #5).

/api/v1/experiments/* is rewritten to mlflow:5000/api/2.0/mlflow/*. The portal reads training
results this way. It is read only: GET, and POST only on paths ending in /search, because MLflow
uses POST for its searches. These tests need no training job: MLflow always has its "Default"
experiment (ID 0). Walk-through step 6 checks a real run once training is delivered.

Start everything first with `make up`, then: `make e2e` (or pytest tests/integration).
"""

import uuid

import httpx
import pytest

DEFAULT_EXPERIMENT = "0"


def assert_error(response, status: int, code: str) -> None:
    """The answer has the status and error code we expect, in the shared error format."""
    assert response.status_code == status, response.text
    error = response.json()["error"]
    assert error["code"] == code
    assert error["message"]
    assert error["request_id"], "every error carries the request ID, to find it in the logs"


def test_searching_experiments_reaches_mlflow(gateway):
    response = gateway.post("/api/v1/experiments/experiments/search", json={"max_results": 50})

    assert response.status_code == 200, response.text
    ids = [experiment["experiment_id"] for experiment in response.json()["experiments"]]
    assert DEFAULT_EXPERIMENT in ids


def test_reading_one_experiment(gateway):
    response = gateway.get(
        "/api/v1/experiments/experiments/get", params={"experiment_id": DEFAULT_EXPERIMENT}
    )

    assert response.status_code == 200, response.text
    assert response.json()["experiment"]["name"] == "Default"


def test_searching_runs(gateway):
    response = gateway.post(
        "/api/v1/experiments/runs/search",
        json={"experiment_ids": [DEFAULT_EXPERIMENT], "max_results": 1},
    )

    assert response.status_code == 200, response.text
    assert isinstance(response.json().get("runs", []), list)


def test_mlflow_errors_come_back_in_the_shared_format(gateway):
    response = gateway.get("/api/v1/experiments/experiments/get", params={"experiment_id": "987654321"})

    assert_error(response, 404, "RESOURCE_DOES_NOT_EXIST")


@pytest.mark.parametrize(
    "path",
    ["/api/v1/experiments/experiments/create", "/api/v1/experiments/runs/create"],
)
def test_writes_to_mlflow_are_blocked(gateway, path):
    name = f"must-not-exist-{uuid.uuid4().hex[:8]}"

    response = gateway.post(path, json={"name": name, "experiment_id": DEFAULT_EXPERIMENT})

    assert_error(response, 405, "METHOD_NOT_ALLOWED")
    missing = gateway.get("/api/v1/experiments/experiments/get-by-name", params={"experiment_name": name})
    assert missing.status_code == 404, "the blocked request must not have reached MLflow"


def test_deleting_through_the_gateway_is_blocked(gateway):
    response = gateway.delete(f"/api/v1/experiments/experiments/{DEFAULT_EXPERIMENT}")

    assert_error(response, 405, "METHOD_NOT_ALLOWED")


def test_mlflow_needs_a_login(gateway):
    url = str(gateway.base_url).rstrip("/") + "/api/v1/experiments/experiments/search"

    response = httpx.post(url, json={}, timeout=30)  # no Authorization header

    assert_error(response, 401, "NOT_AUTHENTICATED")
