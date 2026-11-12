"""The failure-recovery scenario of the final demo: a worker is killed in the middle of a job,
its heartbeat stops, the job goes FAILED, is retried, and finishes.

SKIPPED until Mariam (dead-worker detection by missing heartbeats, retries) and Maitha (worker
recovery) deliver: Sat 21 - Tue 24 Nov. Remove the `skip` line to switch it on.

Run it with short settings in .env, so it takes about a minute instead of several:
    HEARTBEAT_INTERVAL_SECONDS=2
    HEARTBEAT_TIMEOUT_SECONDS=6
    STANDIN_TRAINING_SECONDS=30   (only while the stand-in worker is in use: a job long enough to kill)
then `make up` again.
"""

import subprocess

import pytest

from tests.integration.conftest import REPO, events_of, small_job, tiny_image_dataset, wait_for


def compose(*args: str) -> None:
    """Run a docker compose command for this repo, e.g. compose("kill", "training-worker")."""
    subprocess.run(["docker", "compose", *args], cwd=REPO, check=True, capture_output=True)


@pytest.mark.skip(
    reason="Mariam (dead-worker detection, retries) + Maitha (worker recovery) — Sat 21 to Tue 24 Nov"
)
def test_killed_worker_job_is_retried_and_finishes(gateway):
    project = gateway.post("/api/v1/projects", json={"name": "Failure recovery"}).json()
    dataset = gateway.post(
        "/api/v1/datasets",
        data={"project_id": project["project_id"], "name": "sample", "format": "tar_gz"},
        files={"file": ("sample.tar.gz", tiny_image_dataset(), "application/gzip")},
    ).json()
    job_id = gateway.post(
        "/api/v1/jobs", json=small_job(project["project_id"], dataset["dataset_id"])
    ).json()["job_id"]

    def status() -> str:
        return gateway.get(f"/api/v1/jobs/{job_id}").json()["status"]

    wait_for(lambda: status() == "RUNNING", f"{job_id} to start running")

    # The worker dies mid-job: no more heartbeats.
    compose("kill", "training-worker")
    try:
        failed = wait_for(
            lambda: [e for e in events_of(gateway, job_id) if e["event_type"] == "job.failed"],
            f"{job_id} to be marked FAILED after its heartbeat stopped",
        )
        assert "heartbeat" in (failed[0]["data"]["reason"] or "")
        wait_for(
            lambda: any(e["event_type"] == "job.retrying" for e in events_of(gateway, job_id)),
            f"{job_id} to be retried",
        )
    finally:
        compose("start", "training-worker")  # a worker comes back (in the cloud: a new machine)

    wait_for(lambda: status() == "SUCCEEDED", f"{job_id} to finish on its retry", timeout_seconds=300)
    attempts = [e["data"].get("attempt") for e in events_of(gateway, job_id)]
    assert max(attempts) == 2, "the job finished on its second attempt"
