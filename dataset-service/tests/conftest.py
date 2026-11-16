"""Test helpers.

Unit tests use SQLite and an in-memory object store, so they run with nothing else installed.
The real PostgreSQL + LocalStack path is covered by `make up` and the integration tests.
"""

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.db import SCHEMA, Base
from app.errors import ApiError
from app.main import create_app
from app.storage import MemoryStorage

CONTRACT = Path(__file__).resolve().parents[2] / "contracts" / "openapi" / "dataset-service.yaml"
USER = {"X-User-Id": "user-1"}
STRANGER = {"X-User-Id": "user-stranger"}


class FakeProjects:
    """Membership double for tests. Members of project-01: user-1 only by default."""

    def __init__(self, members: dict[str, set[str]] | None = None) -> None:
        self.members = members or {"project-01": {"user-1"}}

    def require_member(self, project_id: str, user_id: str, request_id: str) -> None:
        allowed = self.members.get(project_id, set())
        if user_id in allowed:
            return
        if project_id not in self.members:
            raise ApiError(404, "PROJECT_NOT_FOUND", f"Project {project_id} does not exist")
        raise ApiError(403, "NOT_A_MEMBER", f"You are not a member of {project_id}")


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    ).execution_options(schema_translate_map={SCHEMA: None})
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def storage():
    return MemoryStorage()


@pytest.fixture
def projects():
    return FakeProjects()


@pytest.fixture
def client(engine, storage, projects):
    with TestClient(create_app(engine, storage, projects)) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def check():
    components = yaml.safe_load(CONTRACT.read_text())["components"]

    def matches(body: dict, schema_name: str) -> None:
        schema = {"$ref": f"#/components/schemas/{schema_name}", "components": components}
        Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(body)

    return matches
