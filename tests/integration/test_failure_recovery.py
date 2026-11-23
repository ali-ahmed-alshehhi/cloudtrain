"""The failure-recovery scenario of the final demo: a worker is killed in the middle of a job,
its heartbeat stops, the job goes FAILED, is retried, and finishes. Mariam (dead-worker detection,
retries) + Maitha (the Scheduler places the retry again) + Abdullah (the real worker's heartbeats).

It runs when the heartbeat settings are short, as in CI (.github/workflows/ci.yml sets them), and
takes about a minute. With the default 120-second timeout it would take many minutes, so it skips.
To run it on a laptop, put these in .env, then `make reset && make up`:
    HEARTBEAT_INTERVAL_SECONDS=2
    HEARTBEAT_TIMEOUT_SECONDS=6
    JOB_SWEEP_INTERVAL_SECONDS=2
    SQS_VISIBILITY_TIMEOUT_SECONDS=20
"""

import subprocess

import pytest

from tests.integration.conftest import REPO, events_of, setting, small_job, tiny_tabular_dataset, wait_for


def compose(*args: str) -> None:
    """Run a docker compose command for this repo, e.g. compose("kill", "training-worker")."""
    subprocess.run(["docker", "compose", *args], cwd=REPO, check=True, capture_output=True)


SHORT_HEARTBEAT = float(setting("HEARTBEAT_TIMEOUT_SECONDS", "120")) <= 30


@pytest.mark.skipif(
    not SHORT_HEARTBEAT,
    reason="needs short heartbeat settings (HEARTBEAT_TIMEOUT_SECONDS<=30), as in CI: see the docstring",
)
def test_killed_worker_job_is_retried_and_finishes(gateway):
    project = gateway.post("/api/v1/projects", json={"name": "Failure recovery"}).json()
    dataset = gateway.post(
        "/api/v1/datasets",
        data={"project_id": project["project_id"], "name": "wisconsin", "format": "csv"},
        files={"file": ("wisconsin.csv", tiny_tabular_dataset(), "text/csv")},
    ).json()
    form = small_job(project["project_id"], dataset["dataset_id"])
    # The real worker trains the tiny table in ~10 s with 1 epoch: too fast to kill it in time.
    # 300 epochs keep it running ~30 s on a laptop, so the worker is killed in the middle of the job.
    form["hyperparameters"]["epochs"] = 300
    job_id = gateway.post("/api/v1/jobs", json=form).json()["job_id"]

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
