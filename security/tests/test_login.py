"""The real login, end to end: Cognito on the AWS Emulator -> token -> gateway -> services.

Owner: Salem (Student 9), task #53. Ali's unit tests (gateway/tests) check the token rules with a
fake key; these tests use REAL Cognito tokens against the WHOLE running system.

Run (needs the AWS Emulator and the real-login stack, see security/login/README.md):
    security/login/setup.sh
    docker compose -f docker-compose.yml -f security/login/compose.login.yml up -d --build --wait
    .venv/bin/python -m pytest security/tests -q
"""

import base64
import json
import os
import subprocess
from pathlib import Path

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

LOGIN = Path(__file__).resolve().parent.parent / "login"
GATEWAY = os.environ.get("GATEWAY_URL", "http://localhost:5810")
PROJECTS = "/api/v1/projects"
DEV_TOKEN = "dev-token-local-only"  # the laptop token from .env.example


def settings() -> dict:
    """The values setup.sh wrote: pool, app clients and issuer (none of them secret)."""
    lines = (LOGIN / ".local" / "login.env").read_text().splitlines()
    return dict(line.split("=", 1) for line in lines if "=" in line)


def token(user: str, *flags: str) -> str:
    """Log in as a test user through Cognito and return the token."""
    result = subprocess.run(
        [str(LOGIN / "token.sh"), user, *flags], check=True, capture_output=True, text=True, timeout=60
    )
    return result.stdout.strip()


def call(bearer: str | None, method: str = "GET", path: str = PROJECTS, **kwargs) -> httpx.Response:
    headers = {"Authorization": f"Bearer {bearer}"} if bearer is not None else {}
    return httpx.request(method, GATEWAY + path, headers=headers, timeout=30, **kwargs)


def claims_of(token_value: str) -> dict:
    """Read a token's claims WITHOUT checking it (only to build test tokens)."""
    return jwt.decode(token_value, options={"verify_signature": False})


def assert_refused(response: httpx.Response) -> None:
    """401 in the shared error format, with a request ID."""
    assert response.status_code == 401, response.text
    error = response.json()["error"]
    assert error["code"] == "NOT_AUTHENTICATED"
    assert error["request_id"]


def b64(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


@pytest.fixture(scope="module")
def alice() -> str:
    return token("alice")


# ---------- A real login works ----------


def test_a_real_cognito_token_is_accepted(alice):
    assert call(alice).status_code == 200


def test_the_token_says_who_and_which_role(alice):
    claims = claims_of(alice)
    login = settings()

    assert claims["iss"] == login["ISSUER"]
    assert claims["aud"] == login["CLIENT_ID"]
    assert claims["token_use"] == "id"
    assert "data-scientist" in claims["cognito:groups"]


# ---------- Everything else is refused (401) ----------


def test_no_token_is_refused():
    assert_refused(call(None))


def test_the_laptop_dev_token_is_refused_once_the_real_login_is_on():
    assert_refused(call(DEV_TOKEN))


def test_a_token_whose_content_was_changed_is_refused(alice):
    header, _, signature = alice.split(".")
    payload = {**claims_of(alice), "sub": "someone-else", "cognito:groups": ["admin"]}

    assert_refused(call(f"{header}.{b64(payload)}.{signature}"))


def test_a_token_signed_with_another_key_is_refused(alice):
    attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    kid = jwt.get_unverified_header(alice)["kid"]  # pretend to be Cognito's key

    forged = jwt.encode(claims_of(alice), attacker_key, algorithm="RS256", headers={"kid": kid})

    assert_refused(call(forged))


def test_an_unsigned_token_is_refused(alice):
    unsigned = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64(claims_of(alice))}."

    assert_refused(call(unsigned))


def test_a_token_made_for_another_app_is_refused():
    assert_refused(call(token("alice", "--other-app")))


def test_an_access_token_is_refused_only_id_tokens_are_accepted():
    # Decision 0006: the gateway checks the audience, which Cognito puts in ID tokens only
    assert_refused(call(token("alice", "--access")))


# ---------- A logged-in user only sees their own projects (403) ----------


def test_users_cannot_open_each_others_projects(alice):
    created = call(alice, "POST", json={"name": "Alice's private project"})
    assert created.status_code == 201, created.text
    project = created.json()
    assert project["owner_id"] == claims_of(alice)["sub"], "the user ID is the Cognito user"

    path = f"{PROJECTS}/{project['project_id']}"
    assert call(alice, path=path).status_code == 200
    for other in ("bob", "vera"):
        bearer = token(other)
        assert call(bearer, path=path).status_code == 403, f"{other} must not open Alice's project"
        listed = [p["project_id"] for p in call(bearer).json()["items"]]
        assert project["project_id"] not in listed, f"{other} must not see Alice's project in the list"
