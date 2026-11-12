"""Health, metrics, logs, request IDs and a database that is down."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.main import create_app
from tests.conftest import ALICE, create


def test_health(client, check):
    response = client.get("/health")

    assert response.status_code == 200
    check(response.json(), "Health")
    assert response.json()["service"] == "project-service"


def test_metrics(client):
    create(client)

    response = client.get("/metrics")

    assert response.status_code == 200
    assert 'project_service_requests_total{endpoint="/projects",method="POST",status="201"}' in response.text


def test_request_id_from_the_gateway_is_kept(client):
    response = client.get("/projects", headers={**ALICE, "X-Request-Id": "req-8f2a"})

    assert response.headers["x-request-id"] == "req-8f2a"


def test_errors_carry_the_request_id(client):
    response = client.get("/projects/project-99", headers={**ALICE, "X-Request-Id": "req-777"})

    assert response.json()["error"]["request_id"] == "req-777"


def test_unknown_path_uses_the_error_format(client, check):
    response = client.get("/nothing-here", headers=ALICE)

    assert response.status_code == 404
    check(response.json(), "Error")


def test_one_json_log_line_per_request(engine, capsys):
    with TestClient(create_app(engine)) as client:
        capsys.readouterr()
        client.get("/projects", headers={**ALICE, "X-Request-Id": "req-log1"})

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    [line] = [line for line in lines if line.get("request_id") == "req-log1"]
    assert {"timestamp", "service", "level", "request_id", "path", "status", "duration_ms"} <= line.keys()
    assert line["service"] == "project-service"


@pytest.fixture
def client_without_database():
    # Nothing listens on port 1, so every database call fails at once.
    engine = create_engine(
        "postgresql+psycopg://user:pw@127.0.0.1:1/none", connect_args={"connect_timeout": 1}
    )
    with TestClient(create_app(engine)) as test_client:
        yield test_client


def test_health_is_503_when_the_database_is_down(client_without_database, check):
    response = client_without_database.get("/health")

    assert response.status_code == 503
    check(response.json(), "Error")


def test_requests_get_503_when_the_database_is_down(client_without_database, check):
    response = client_without_database.get("/projects", headers=ALICE)

    assert response.status_code == 503
    check(response.json(), "Error")
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
