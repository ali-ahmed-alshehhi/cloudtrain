"""Test helpers.

Unit tests use a small in-memory SQLite database instead of PostgreSQL, so they run in a second
with nothing else installed. SQLite has no schemas, so the `projects` schema is mapped away.
The real PostgreSQL path (migrations included) is covered by `make up` and the integration tests.
"""

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.db import SCHEMA, Base
from app.main import create_app

CONTRACT = Path(__file__).resolve().parents[2] / "contracts" / "openapi" / "project-service.yaml"

ALICE = {"X-User-Id": "user-alice"}
BOB = {"X-User-Id": "user-bob"}


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    ).execution_options(schema_translate_map={SCHEMA: None})
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def client(engine):
    with TestClient(create_app(engine)) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def contract() -> dict:
    return yaml.safe_load(CONTRACT.read_text())


@pytest.fixture
def check(contract):
    """check(body, "Project") fails the test if the body does not match that schema in the contract."""

    def matches(body: dict, schema_name: str) -> None:
        schema = {"$ref": f"#/components/schemas/{schema_name}", "components": contract["components"]}
        validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
        validator.validate(body)

    return matches


def create(client, name="Image Classification", headers=ALICE, **extra_headers) -> dict:
    response = client.post("/projects", json={"name": name}, headers={**headers, **extra_headers})
    assert response.status_code == 201, response.text
    return response.json()
