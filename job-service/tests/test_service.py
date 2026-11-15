"""The service as a whole: it keeps its contract, and refuses unsafe settings."""

import pytest
import yaml

from app.settings import Settings
from tests.conftest import CONTRACTS

METHODS = {"get", "post", "put", "patch", "delete"}


def operations(paths: dict) -> set[tuple[str, str]]:
    return {(path, method) for path, item in paths.items() for method in item if method in METHODS}


def test_every_contract_address_exists_and_nothing_extra(client):
    contract = yaml.safe_load((CONTRACTS / "openapi" / "job-service.yaml").read_text())

    assert operations(client.app.openapi()["paths"]) == operations(contract["paths"])


def test_a_heartbeat_timeout_shorter_than_3_intervals_is_refused():
    with pytest.raises(ValueError, match="at least 3"):
        Settings(heartbeat_interval_seconds=30, heartbeat_timeout_seconds=60).check()


def test_metrics_include_job_counters(client):
    from tests.conftest import submit

    submit(client)
    text = client.get("/metrics").text

    assert "job_service_jobs_submitted_total" in text
    assert 'job_service_status_changes_total{status="QUEUED"}' in text


def test_every_answer_carries_a_request_id(client):
    response = client.get("/health", headers={"X-Request-Id": "req-abc"})
    assert response.headers["X-Request-Id"] == "req-abc"
