"""The final-demo walk-through (docs/ARCHITECTURE.md, section 18), run through the gateway.

Steps 2-5 and 7 run for real now (against the stand-ins where owners have not delivered yet).
The other steps are written but SKIPPED, with the owner and the hand-off date: when you deliver,
remove the `skip` line of your step and make it pass.

The steps share what they create (project -> dataset -> job), so run the whole file, in order.
"""

import re

import pytest

from tests.integration.conftest import events_of, small_job, tiny_image_dataset, wait_for


@pytest.fixture(scope="module")
def project(gateway) -> dict:
    response = gateway.post("/api/v1/projects", json={"name": "Image Classification"})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture(scope="module")
def dataset(gateway, project) -> dict:
    response = gateway.post(
        "/api/v1/datasets",
        data={"project_id": project["project_id"], "name": "cifar-10 (tiny sample)", "format": "tar_gz"},
        files={"file": ("cifar10-sample.tar.gz", tiny_image_dataset(), "application/gzip")},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture(scope="module")
def job(gateway, project, dataset) -> dict:
    response = gateway.post("/api/v1/jobs", json=small_job(project["project_id"], dataset["dataset_id"]))
    assert response.status_code == 202, response.text
    return response.json()


@pytest.fixture(scope="module")
def finished_job(gateway, job) -> dict:
    """The job once it has reached a final status."""

    def final():
        found = gateway.get(f"/api/v1/jobs/{job['job_id']}").json()
        return found if found["status"] in ("SUCCEEDED", "FAILED", "CANCELLED") else None

    return wait_for(final, f"{job['job_id']} to finish")


# ---------- 1. Log in (Salem) ----------


@pytest.mark.skip(reason="Salem: real login in the gateway — hand-off Fri 20 Nov")
def test_step_01_log_in(gateway):
    """Sign in with the real login provider and use its token for every step below."""


def test_requests_without_login_are_refused(gateway):
    """Until Salem's step works: the gateway already refuses requests with no valid token."""
    response = gateway.get("/api/v1/projects", headers={"Authorization": "Bearer wrong"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"


# ---------- 2-5, 7: run now ----------


def test_step_02_create_project(project):
    assert re.fullmatch(r"project-[0-9]+", project["project_id"])
    assert project["name"] == "Image Classification"


def test_step_03_upload_dataset(gateway, dataset):
    assert re.fullmatch(r"dataset-[0-9]+", dataset["dataset_id"])
    assert dataset["latest_version"] == 1
    version = gateway.get(f"/api/v1/datasets/{dataset['dataset_id']}/versions/1").json()
    assert re.fullmatch(r"[a-f0-9]{64}", version["checksum_sha256"])


def test_step_04_submit_job(job):
    assert re.fullmatch(r"job-[0-9]+", job["job_id"])
    assert job["status"] == "QUEUED"


def test_step_05_queued_then_scheduled_then_running(gateway, job, finished_job):
    steps = [e["event_type"] for e in events_of(gateway, job["job_id"])]

    assert steps[:3] == ["job.queued", "job.scheduled", "job.running"]
    assert finished_job["machine_type"], "the Scheduler must report the machine it chose"


@pytest.mark.skip(
    reason="Abdullah; Ahmed + Abdulla: real training with live MLflow metrics, model in S3 — Fri 20 Nov"
)
def test_step_06_training_tracked_in_mlflow(gateway, finished_job):
    """The job's MLflow run has parameters and metrics (GET /api/v1/experiments/runs/search),
    and its model files are in the artifacts bucket."""


def test_step_07_job_succeeded_and_alert_is_in_the_feed(gateway, finished_job):
    assert finished_job["status"] == "SUCCEEDED"
    assert [h["status"] for h in finished_job["history"]] == ["QUEUED", "SCHEDULED", "RUNNING", "SUCCEEDED"]
    feed = gateway.get("/api/v1/jobs/events", params={"project_id": finished_job["project_id"]}).json()
    assert any(
        e["job_id"] == finished_job["job_id"] and e["event_type"] == "job.succeeded" for e in feed["items"]
    ), "the alert feed (what the portal shows) must contain job.succeeded"


@pytest.mark.skip(reason="Maitha: the machine is released after the job — Fri 20 Nov")
def test_step_07b_machine_released(gateway, finished_job):
    """After SUCCEEDED, the Scheduler has released the job's machine (no worker still running it)."""


# ---------- 8-12: switched on as owners deliver ----------


@pytest.mark.skip(reason="Hilal + Adel; Ahmed + Abdulla: single-GPU vs DDP comparison — Tue 24 Nov")
def test_step_08_compare_single_gpu_and_ddp(gateway):
    """Two finished runs of the same model, strategy 'single' and 'ddp', both visible in MLflow
    with time, throughput and GPU-hours to compare."""


@pytest.mark.skip(
    reason="Majed: register a real model from the MLflow run (needs Abdullah's model, Fri 20 Nov)"
)
def test_step_09_register_best_model(gateway, finished_job):
    """POST /api/v1/models with the job's MLflow run ID -> 201, version 1."""


@pytest.mark.skip(reason="Majed: promote v1; inference passes /health before taking traffic — Tue 24 Nov")
def test_step_10_promote_version_1(gateway):
    """POST /api/v1/models/{id}/versions/1/promote -> 200; GET .../production shows version 1."""


@pytest.mark.skip(reason="Majed: inference loads the live version and predicts — Fri 20 Nov")
def test_step_11_predict(gateway):
    """POST /api/v1/predict with an image -> 200 and a prediction from the live model version."""


@pytest.mark.skip(
    reason="Mariam: GPU-hours and cost per job (Fri 20 Nov); Hilal + Adel: cost page (Tue 24 Nov)"
)
def test_step_12_compute_usage_and_cost(gateway, finished_job):
    """The finished job reports gpu_hours and estimated_cost_usd from contracts/pricing.yaml."""
