"""Test helpers: `check(body, "SchemaName")` fails if an answer does not match the contract."""

from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

CONTRACT = Path(__file__).resolve().parents[2] / "contracts" / "openapi" / "dataset-service.yaml"
USER = {"X-User-Id": "user-1"}


@pytest.fixture(scope="session")
def check():
    components = yaml.safe_load(CONTRACT.read_text())["components"]

    def matches(body: dict, schema_name: str) -> None:
        schema = {"$ref": f"#/components/schemas/{schema_name}", "components": components}
        Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(body)

    return matches
