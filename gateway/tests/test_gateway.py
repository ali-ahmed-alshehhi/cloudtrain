"""Login, headers, internal paths, timeouts, errors, CORS, health, metrics and logs."""

import json
from datetime import UTC, datetime, timedelta

import httpx
import jsonschema
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app import auth
from app.config import load_settings
from app.main import create_app
from tests.conftest import AUTH

# ---------- login ----------


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer wrong-token"},
        {"Authorization": "test-token"},
        {"Authorization": "Bearer "},
    ],
)
def test_401_without_a_valid_token(client, services, error_schema, headers):
    response = client.get("/api/v1/projects", headers=headers)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"
    jsonschema.validate(response.json(), error_schema)
    assert services.received == []


def test_dev_login_is_refused_outside_a_laptop(local_env):
    local_env.setenv("ENVIRONMENT", "dev")  # the cloud dev environment

    with pytest.raises(ValueError, match="only allowed when ENVIRONMENT=local"):
        load_settings()


@pytest.fixture
def jwt_client(local_env, services):
    """A gateway in real-login mode, with a fake login provider's key."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    class FakeKeyStore:
        def get_signing_key_from_jwt(self, token):
            return jwt.PyJWK.from_dict(
                {**json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key())), "alg": "RS256"}
            )

    local_env.setenv("ENVIRONMENT", "dev")
    local_env.setenv("AUTH_MODE", "jwt")
    local_env.setenv("JWT_JWKS_URL", "https://login.test/jwks")
    local_env.setenv("JWT_ISSUER", "https://login.test")
    local_env.setattr(auth, "_jwks_client", lambda url: FakeKeyStore())

    def make_token(expires_in_minutes: int) -> str:
        claims = {
            "sub": "user-42",
            "iss": "https://login.test",
            "exp": datetime.now(UTC) + timedelta(minutes=expires_in_minutes),
        }
        return jwt.encode(claims, private_key, algorithm="RS256")

    with TestClient(create_app(transport=httpx.MockTransport(services.handle))) as test_client:
        yield test_client, make_token


def test_real_login_token_is_accepted(jwt_client, services):
    client, make_token = jwt_client

    response = client.get("/api/v1/projects", headers={"Authorization": f"Bearer {make_token(10)}"})

    assert response.status_code == 200
    assert services.last.headers["x-user-id"] == "user-42"


def test_expired_login_token_is_refused(jwt_client):
    client, make_token = jwt_client

    response = client.get("/api/v1/projects", headers={"Authorization": f"Bearer {make_token(-1)}"})

    assert response.status_code == 401


def test_dev_token_is_refused_in_real_login_mode(jwt_client):
    client, _ = jwt_client

    assert client.get("/api/v1/projects", headers=AUTH).status_code == 401


# ---------- headers ----------


def test_user_id_comes_from_the_token_not_the_caller(client, services):
    client.get("/api/v1/projects", headers={**AUTH, "X-User-Id": "someone-else"})

    assert services.last.headers["x-user-id"] == "user-1"
    assert "authorization" not in services.last.headers  # the token stays at the gateway


def test_request_id_is_passed_through(client, services):
    response = client.get("/api/v1/projects", headers={**AUTH, "X-Request-Id": "req-8f2a"})

    assert services.last.headers["x-request-id"] == "req-8f2a"
    assert response.headers["x-request-id"] == "req-8f2a"


def test_request_id_is_created_when_missing(client, services):
    response = client.get("/api/v1/projects", headers=AUTH)

    created = response.headers["x-request-id"]
    assert created.startswith("req-")
    assert services.last.headers["x-request-id"] == created


def test_unsafe_request_id_is_replaced(client, services):
    client.get("/api/v1/projects", headers={**AUTH, "X-Request-Id": "bad id\nwith newline"})

    assert services.last.headers["x-request-id"].startswith("req-")


# ---------- internal paths ----------


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/jobs/internal/jobs/job-1/status",
        "/api/v1/datasets/internal/datasets/dataset-1/versions/1/download-url",
        "/api/v1/jobs/INTERNAL/x",
        "/api/v1/jobs/%69nternal/x",  # "internal" written in URL code
        "/api/v1/jobs/../internal/x",
        "/internal/run",
    ],
)
def test_internal_paths_are_never_public(client, services, error_schema, path):
    response = client.post(path, headers=AUTH, json={})

    assert response.status_code == 404
    jsonschema.validate(response.json(), error_schema)
    assert services.received == []


# ---------- service down or slow ----------


@pytest.mark.parametrize("address", ["http://job-service-down:8003", "http://job-service-slow:8003"])
def test_503_when_a_service_is_down_or_slow(local_env, services, error_schema, address):
    local_env.setenv("JOB_SERVICE_URL", address)

    with TestClient(create_app(transport=httpx.MockTransport(services.handle))) as client:
        response = client.get("/api/v1/jobs/job-104", headers=AUTH)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
    jsonschema.validate(response.json(), error_schema)


def test_normal_requests_wait_10_seconds(client, services):
    client.get("/api/v1/jobs", headers=AUTH)

    assert services.last.extensions["timeout"]["read"] == 10


def test_uploads_wait_300_seconds_and_keep_their_body(client, services):
    response = client.post(
        "/api/v1/datasets",
        headers=AUTH,
        data={"project_id": "project-01", "name": "cifar10", "format": "tar_gz"},
        files={"file": ("cifar.tar.gz", b"x" * 5000, "application/gzip")},
    )

    assert services.last.extensions["timeout"]["read"] == 300
    assert response.json()["body_size"] > 5000


# ---------- CORS ----------


def test_cors_allows_the_local_portal(client):
    response = client.options(
        "/api/v1/projects",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_refuses_other_websites(client):
    response = client.options(
        "/api/v1/projects",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )

    assert "access-control-allow-origin" not in response.headers


# ---------- health, metrics, logs ----------


def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "gateway"}


def test_metrics_count_requests(client):
    client.get("/api/v1/projects", headers=AUTH)

    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert 'gateway_requests_total{method="GET",route="projects",status="200"}' in response.text


def test_one_json_log_line_per_request(local_env, services, capsys):
    with TestClient(create_app(transport=httpx.MockTransport(services.handle))) as client:
        capsys.readouterr()  # forget start-up output
        client.get("/api/v1/jobs", headers={**AUTH, "X-Request-Id": "req-log1"})

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    request_lines = [line for line in lines if line.get("request_id") == "req-log1"]
    assert len(request_lines) == 1
    line = request_lines[0]
    assert {"timestamp", "service", "level", "request_id", "path", "status", "duration_ms"} <= line.keys()
    assert line["service"] == "gateway"
    assert line["status"] == 200
