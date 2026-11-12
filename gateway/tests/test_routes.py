"""Every route in routes.yaml goes to the right service, with the right path and methods."""

import jsonschema
import pytest

from tests.conftest import AUTH

# public path -> where the gateway must forward it (from the routes table in docs/ARCHITECTURE.md)
ROUTES = [
    ("/api/v1/users/me", "http://project-service:8001/users/me"),
    ("/api/v1/projects", "http://project-service:8001/projects"),
    ("/api/v1/projects/project-01/members", "http://project-service:8001/projects/project-01/members"),
    ("/api/v1/datasets?project_id=project-01", "http://dataset-service:8002/datasets?project_id=project-01"),
    ("/api/v1/datasets/dataset-07/versions/2", "http://dataset-service:8002/datasets/dataset-07/versions/2"),
    ("/api/v1/jobs/job-104", "http://job-service:8003/jobs/job-104"),
    ("/api/v1/jobs/events?after=event-5", "http://job-service:8003/jobs/events?after=event-5"),
    ("/api/v1/experiments/runs/get?run_id=abc1", "http://mlflow:5000/api/2.0/mlflow/runs/get?run_id=abc1"),
    ("/api/v1/models/model-03/production", "http://model-registry:8006/models/model-03/production"),
    ("/api/v1/predict", "http://inference-service:8007/predict"),
]


@pytest.mark.parametrize(("public_path", "expected_url"), ROUTES)
def test_each_route_forwards_to_its_service(client, services, public_path, expected_url):
    response = client.get(public_path, headers=AUTH)

    assert response.status_code == 200
    assert str(services.last.url) == expected_url


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_all_methods_allowed_on_normal_routes(client, services, method):
    response = client.request(method, "/api/v1/jobs/job-104", headers=AUTH, json={})

    assert response.status_code == 200
    assert services.last.method == method


def test_post_allowed_on_experiments_search(client, services):
    response = client.post("/api/v1/experiments/runs/search", headers=AUTH, json={"experiment_ids": ["1"]})

    assert response.status_code == 200
    assert str(services.last.url) == "http://mlflow:5000/api/2.0/mlflow/runs/search"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/v1/experiments/runs/create"),
        ("POST", "/api/v1/experiments/runs/delete"),
        ("DELETE", "/api/v1/experiments/experiments/1"),
        ("PUT", "/api/v1/experiments/runs/search"),
    ],
)
def test_experiments_are_read_only(client, services, error_schema, method, path):
    response = client.request(method, path, headers=AUTH, json={})

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
    assert response.headers["allow"] in ("GET", "GET, POST")  # HTTP: say what IS allowed
    jsonschema.validate(response.json(), error_schema)
    assert services.received == []  # MLflow was never called


@pytest.mark.parametrize("path", ["/health", "/metrics"])
def test_gateway_own_endpoints_are_get_only(client, path):
    response = client.put(path)

    assert response.status_code == 405
    assert response.headers["allow"] == "GET"


def test_mlflow_errors_are_translated_to_the_shared_format(client, error_schema):
    response = client.get("/api/v1/experiments/runs/get?run_id=missing", headers=AUTH)

    assert response.status_code == 404
    jsonschema.validate(response.json(), error_schema)
    assert response.json()["error"]["code"] == "RESOURCE_DOES_NOT_EXIST"


@pytest.mark.parametrize("path", ["/api/v1/unknown", "/api/v1/projectsX", "/somewhere"])
def test_unknown_paths_are_404(client, services, path):
    response = client.get(path, headers=AUTH)

    assert response.status_code == 404
    assert services.received == []
