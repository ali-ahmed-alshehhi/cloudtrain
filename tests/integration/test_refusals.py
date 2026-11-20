"""Requests the platform must REFUSE, run through the gateway with the real services (task #4).

The walk-through checks the happy path. These tests check that a bad training job is stopped at
submit time, with a clear error in the shared format, and never reaches the queue:
- a project that does not exist, a dataset that does not exist, a version that does not exist
- a dataset that belongs to another project (otherwise project A could train on project B's data)
- the alert feed of a project the caller is not a member of

Start everything first with `make up`, then: `make e2e` (or pytest tests/integration).
"""

import pytest

from tests.integration.conftest import small_job, tiny_image_dataset

UNKNOWN_PROJECT = "project-999999"
UNKNOWN_DATASET = "dataset-999999"


def new_project(gateway, name: str) -> str:
    response = gateway.post("/api/v1/projects", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["project_id"]


def new_dataset(gateway, project_id: str) -> str:
    response = gateway.post(
        "/api/v1/datasets",
        data={"project_id": project_id, "name": "refusal test data", "format": "tar_gz"},
        files={"file": ("sample.tar.gz", tiny_image_dataset(), "application/gzip")},
    )
    assert response.status_code == 201, response.text
    return response.json()["dataset_id"]


@pytest.fixture(scope="module")
def own_project(gateway) -> dict:
    """A project with one dataset, used only by these tests."""
    project_id = new_project(gateway, "Refusal tests")
    return {"project_id": project_id, "dataset_id": new_dataset(gateway, project_id)}


@pytest.fixture(scope="module")
def other_project(gateway) -> dict:
    """A second project of the same user, with its own dataset."""
    project_id = new_project(gateway, "Refusal tests (other project)")
    return {"project_id": project_id, "dataset_id": new_dataset(gateway, project_id)}


def assert_refused(response, status: int, code: str) -> None:
    """The answer has the status and error code we expect, in the shared error format."""
    assert response.status_code == status, response.text
    error = response.json()["error"]
    assert error["code"] == code
    assert error["message"]
    assert error["request_id"], "every error carries the request ID, to find it in the logs"


def test_job_for_a_project_that_does_not_exist_is_refused(gateway, own_project):
    job = small_job(UNKNOWN_PROJECT, own_project["dataset_id"])

    assert_refused(gateway.post("/api/v1/jobs", json=job), 404, "PROJECT_NOT_FOUND")


def test_job_with_a_dataset_that_does_not_exist_is_refused(gateway, own_project):
    job = small_job(own_project["project_id"], UNKNOWN_DATASET)

    assert_refused(gateway.post("/api/v1/jobs", json=job), 404, "DATASET_NOT_FOUND")


def test_job_with_a_version_that_does_not_exist_is_refused(gateway, own_project):
    job = {**small_job(own_project["project_id"], own_project["dataset_id"]), "dataset_version": 99}

    assert_refused(gateway.post("/api/v1/jobs", json=job), 404, "DATASET_VERSION_NOT_FOUND")


def test_job_with_a_dataset_of_another_project_is_refused(gateway, own_project, other_project):
    job = small_job(own_project["project_id"], other_project["dataset_id"])

    assert_refused(gateway.post("/api/v1/jobs", json=job), 422, "DATASET_NOT_IN_PROJECT")


def test_refused_jobs_are_never_saved(gateway, own_project):
    """Runs after the refusals above: the project still has no job at all."""
    response = gateway.get("/api/v1/jobs", params={"project_id": own_project["project_id"]})

    assert response.status_code == 200, response.text
    assert response.json()["items"] == []


def test_alert_feed_of_a_project_you_are_not_in_is_refused(gateway):
    response = gateway.get("/api/v1/jobs/events", params={"project_id": UNKNOWN_PROJECT})

    assert_refused(response, 403, "NOT_A_MEMBER")
