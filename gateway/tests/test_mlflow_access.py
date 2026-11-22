"""Only project members can read a project's MLflow runs (#107).

In the fake services, user-1 (the dev login) is a member of project-01 only. MLflow runs are
tagged with project_id: "mine" and "abc1" are in project-01, "theirs" and "other" in project-02.
"""

import httpx
import jsonschema
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import AUTH, FakeServices


def test_search_returns_only_runs_of_my_projects(client):
    response = client.post("/api/v1/experiments/runs/search", headers=AUTH, json={"experiment_ids": ["1"]})

    assert response.status_code == 200
    assert [run["info"]["run_id"] for run in response.json()["runs"]] == ["mine"]
    assert response.json()["next_page_token"] == "page-2"  # paging still works


def test_search_sends_the_request_body_to_mlflow(client, services):
    client.post("/api/v1/experiments/runs/search", headers=AUTH, json={"filter": "tags.job_id = 'job-1'"})

    assert b"tags.job_id = 'job-1'" in services.last.content


def test_my_run_can_be_read(client):
    response = client.get("/api/v1/experiments/runs/get?run_id=abc1", headers=AUTH)

    assert response.status_code == 200
    assert response.json()["run"]["info"]["run_id"] == "abc1"


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/experiments/runs/get?run_id=other",
        "/api/v1/experiments/metrics/get-history?run_id=other&metric_key=accuracy",
    ],
)
def test_another_projects_run_looks_like_it_does_not_exist(client, services, error_schema, path):
    response = client.get(path, headers=AUTH)

    assert response.status_code == 404
    jsonschema.validate(response.json(), error_schema)
    assert response.json()["error"]["code"] == "RESOURCE_DOES_NOT_EXIST"
    assert not str(services.last.url).endswith("metric_key=accuracy"), "metrics were never asked for"


def test_metrics_of_my_run_are_forwarded(client, services):
    response = client.get("/api/v1/experiments/metrics/get-history?run_id=abc1&metric_key=f1", headers=AUTH)

    assert response.status_code == 200
    assert (
        str(services.last.url)
        == "http://mlflow:5000/api/2.0/mlflow/metrics/get-history?run_id=abc1&metric_key=f1"
    )


def test_experiments_are_passed_through(client, services):
    response = client.get(
        "/api/v1/experiments/experiments/get-by-name?experiment_name=cloudtrain", headers=AUTH
    )

    assert response.status_code == 200
    assert "/projects" not in str(services.last.url)


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/experiments/artifacts/list?run_id=other",
        "/api/v1/experiments/registered-models/get?name=m",
        "/api/v1/experiments/runs",
    ],
)
def test_other_mlflow_endpoints_are_not_public(client, services, path):
    response = client.get(path, headers=AUTH)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    assert all(request.url.host != "mlflow" for request in services.received)


def test_a_run_id_is_required(client):
    response = client.get("/api/v1/experiments/metrics/get-history?metric_key=f1", headers=AUTH)

    assert response.status_code == 400


def test_503_when_projects_cannot_be_checked(local_env, error_schema):
    local_env.setenv("PROJECT_SERVICE_URL", "http://project-service-down:8001")
    services = FakeServices()
    with TestClient(create_app(transport=httpx.MockTransport(services.handle))) as client:
        response = client.post("/api/v1/experiments/runs/search", headers=AUTH, json={})

    assert response.status_code == 503
    jsonschema.validate(response.json(), error_schema)
    assert all(request.url.host != "mlflow" for request in services.received)
