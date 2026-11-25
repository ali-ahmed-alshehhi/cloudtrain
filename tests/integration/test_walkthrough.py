"""The final-demo walk-through (docs/ARCHITECTURE.md, section 18), run through the gateway.

Steps 2-12 run for real now. Step 6 asserts Abdullah's live MLflow metrics after the
real training worker finishes, and step 9 registers that run's model. Steps 10-11 serve the
small image test model (see `image_model`), because /predict takes an image and the walk-through
job is tabular. Step 1 runs with the real login (`make e2e-login`, and the Login workflow in
CI); `make e2e` uses the laptop dev token and skips it. The other steps
are written but SKIPPED, with the owner and the hand-off date: when you deliver, remove
the `skip` line of your step and make it pass.

The steps share what they create (project -> dataset -> job), so run the whole file, in order.
"""

import base64
import json
import os
import re
import subprocess
import time

import httpx
import pytest

from tests.integration.conftest import (
    REPO,
    class_image,
    events_of,
    links_of,
    log_image_test_model,
    real_login,
    setting,
    small_job,
    tiny_tabular_dataset,
    wait_for,
)


@pytest.fixture(scope="module")
def project(gateway) -> dict:
    response = gateway.post("/api/v1/projects", json={"name": "Wisconsin Breast Cancer"})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture(scope="module")
def dataset(gateway, project) -> dict:
    response = gateway.post(
        "/api/v1/datasets",
        data={
            "project_id": project["project_id"],
            "name": "wisconsin-breast-cancer (tiny sample)",
            "format": "csv",
        },
        files={"file": ("wisconsin.csv", tiny_tabular_dataset(), "text/csv")},
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

    return wait_for(final, f"{job['job_id']} to finish", timeout_seconds=300)


# ---------- 1. Log in (Salem) ----------


def test_step_01_log_in(gateway):
    """Alice signs in with the real login (Cognito) and every step below uses her ID token.
    Salem's security/tests check the token rules in depth; this checks the demo uses the real login."""
    if not real_login():
        pytest.skip("`make up` uses the dev token; `make e2e-login` runs this step with the real login")
    token = gateway.headers["Authorization"].removeprefix("Bearer ")
    payload = token.split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))

    assert claims["token_use"] == "id"
    assert claims["cognito:username"] == "alice"
    assert gateway.get("/api/v1/projects").status_code == 200
    dev = {"Authorization": f"Bearer {setting('DEV_AUTH_TOKEN')}"}
    assert gateway.get("/api/v1/projects", headers=dev).status_code == 401, "dev token must be off"


def test_requests_without_login_are_refused(gateway):
    """With either login, the gateway refuses requests with no valid token."""
    response = gateway.get("/api/v1/projects", headers={"Authorization": "Bearer wrong"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"


# ---------- 2-7, 12: run now ----------


def test_step_02_create_project(project):
    assert re.fullmatch(r"project-[0-9]+", project["project_id"])
    assert project["name"] == "Wisconsin Breast Cancer"


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


def test_step_06_training_tracked_in_mlflow(gateway, finished_job):
    """The job's MLflow run has parameters and metrics (GET /api/v1/experiments/runs/search),
    and its model files are in the artifacts bucket."""
    assert finished_job["status"] == "SUCCEEDED", finished_job
    experiment = gateway.get(
        "/api/v1/experiments/experiments/get-by-name",
        params={"experiment_name": "cloudtrain"},
    )
    assert experiment.status_code == 200, experiment.text
    experiment_id = experiment.json()["experiment"]["experiment_id"]
    response = gateway.post(
        "/api/v1/experiments/runs/search",
        json={
            "experiment_ids": [experiment_id],
            "filter": (
                f"tags.job_id = '{finished_job['job_id']}' "
                f"and tags.project_id = '{finished_job['project_id']}'"
            ),
            "max_results": 10,
        },
    )
    assert response.status_code == 200, response.text
    runs = response.json().get("runs") or []
    assert runs, "expected at least one MLflow run tagged with the finished job"
    data = runs[0].get("data", runs[0])
    params = (
        {item["key"]: item["value"] for item in data.get("params", [])}
        if isinstance(data.get("params"), list)
        else data.get("params", {})
    )
    metrics = (
        {item["key"]: item.get("value") for item in data.get("metrics", [])}
        if isinstance(data.get("metrics"), list)
        else data.get("metrics", {})
    )
    assert params.get("model") == "tabular_mlp"
    assert {"accuracy", "f1", "validation_loss", "train_loss"} & set(metrics)


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
    assert finished_job["status"] == "SUCCEEDED"

    def scheduler_metrics() -> dict[str, float]:
        out = subprocess.run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "scheduler",
                "python",
                "-c",
                'import urllib.request; print(urllib.request.urlopen("http://localhost:8004/metrics").read().decode())',
            ],
            capture_output=True,
            timeout=30,
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        )
        assert out.returncode == 0, f"docker compose exec failed: {out.stderr.decode()}"
        text = out.stdout.decode()
        values: dict[str, float] = {}
        for name in ("scheduler_workers_busy", "scheduler_gpus_in_use"):
            match = re.search(rf"^{name}\s+([\d.]+)", text, re.MULTILINE)
            if match:
                values[name] = float(match.group(1))
        return values

    # The scheduler frees finished slots when the queue is empty; wait up to 60 s
    for _ in range(12):
        metrics = scheduler_metrics()
        if metrics.get("scheduler_workers_busy", 1) == 0:
            break
        time.sleep(5)

    assert metrics["scheduler_workers_busy"] == 0, f"expected 0 busy workers, got {metrics}"
    assert metrics["scheduler_gpus_in_use"] == 0, f"expected 0 GPUs in use, got {metrics}"


# ---------- 8-12: switched on as owners deliver ----------


def test_step_08_compare_single_gpu_and_ddp(gateway, project, finished_job):
    """Two finished runs of the same model, strategy 'single' and 'ddp', both visible in MLflow
    with time, throughput and GPU-hours to compare. Same form as Ahmed + Abdulla's comparison
    (training/distributed/platform_compare.py, #30) on the full Wisconsin CSV, which is big enough
    to split over 2 processes. On a laptop both processes run on the CPU (decision 0011), so this
    checks the plumbing, not a speedup."""
    csv = REPO / "training" / "distributed" / "data" / "wisconsin.csv"
    uploaded = gateway.post(
        "/api/v1/datasets",
        data={"project_id": project["project_id"], "name": "wisconsin-breast-cancer", "format": "csv"},
        files={"file": ("wisconsin.csv", csv.read_bytes(), "text/csv")},
    )
    assert uploaded.status_code == 201, uploaded.text

    finished = {}
    for strategy, processes in (("single", 1), ("ddp", 2)):
        form = small_job(project["project_id"], uploaded.json()["dataset_id"])
        form["hyperparameters"].update(epochs=2, batch_size=16)
        form["resources"]["gpu_count"] = processes  # the contract: for ddp, world_size = gpu_count
        form["parallelism"] = {"strategy": strategy, "world_size": processes}
        submitted = gateway.post("/api/v1/jobs", json=form)
        assert submitted.status_code == 202, submitted.text
        job_id = submitted.json()["job_id"]

        def final(job_id=job_id):
            found = gateway.get(f"/api/v1/jobs/{job_id}").json()
            return found if found["status"] in ("SUCCEEDED", "FAILED", "CANCELLED") else None

        finished[strategy] = wait_for(final, f"the {strategy} job to finish", timeout_seconds=300)
        assert finished[strategy]["status"] == "SUCCEEDED", finished[strategy]

    for strategy, job in finished.items():
        run_id = mlflow_run_id_of(gateway, job)
        run = gateway.get("/api/v1/experiments/runs/get", params={"run_id": run_id})
        assert run.status_code == 200, run.text
        tags = {tag["key"]: tag["value"] for tag in run.json()["run"]["data"].get("tags", [])}
        assert tags["strategy"] == strategy
        for key in ("epoch_seconds", "epoch_images"):  # what the comparison page reads (#76)
            history = gateway.get(
                "/api/v1/experiments/metrics/get-history", params={"run_id": run_id, "metric_key": key}
            )
            assert history.status_code == 200, history.text
            values = [point["value"] for point in history.json().get("metrics", [])]
            assert len(values) == 2 and all(value > 0 for value in values), (strategy, key, values)
        assert job["gpu_hours"] is not None and job["estimated_cost_usd"] is not None


def mlflow_run_id_of(gateway, job: dict) -> str:
    experiment = gateway.get(
        "/api/v1/experiments/experiments/get-by-name", params={"experiment_name": "cloudtrain"}
    ).json()["experiment"]
    response = gateway.post(
        "/api/v1/experiments/runs/search",
        json={
            "experiment_ids": [experiment["experiment_id"]],
            "filter": f"tags.job_id = '{job['job_id']}' and tags.project_id = '{job['project_id']}'",
            "max_results": 1,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["runs"][0]["info"]["run_id"]


def register(gateway, job: dict, name: str, run_id: str) -> httpx.Response:
    return gateway.post("/api/v1/models", json={**links_of(job), "name": name, "mlflow_run_id": run_id})


@pytest.fixture(scope="module")
def tabular_model(gateway, finished_job) -> dict:
    """Step 9: the walk-through job's own run (the tabular MLP) registered as version 1."""
    response = register(gateway, finished_job, "wisconsin-mlp", mlflow_run_id_of(gateway, finished_job))
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture(scope="module")
def image_model(gateway, finished_job) -> dict:
    """Steps 10-11: /predict takes an image, so they use the small CIFAR-10-shaped image model
    (inference-service/app/fixture_model.py), logged as an MLflow run linked to the same job."""
    response = register(gateway, finished_job, "cifar10-classifier", log_image_test_model(finished_job))
    assert response.status_code == 201, response.text
    return response.json()


def test_step_09_register_best_model(gateway, finished_job, tabular_model):
    """POST /api/v1/models with the job's MLflow run ID -> 201, version 1."""
    assert tabular_model["version"] == 1
    assert tabular_model["mlflow_run_id"] == mlflow_run_id_of(gateway, finished_job)
    assert tabular_model["job_id"] == finished_job["job_id"]
    assert tabular_model["dataset_id"] == finished_job["spec"]["dataset_id"]
    assert {"accuracy", "f1"} <= set(tabular_model["metrics"])
    assert tabular_model["artifact_uri"].startswith("s3://"), tabular_model
    assert tabular_model["stage"] == "none"


def test_step_10_promote_version_1(gateway, tabular_model, image_model):
    """POST /api/v1/models/{id}/versions/1/promote -> 200; GET .../production shows version 1.
    A version that fails inference's health check never takes traffic: the tabular model
    cannot classify an image, so its promotion is refused and nothing goes live."""
    refused = gateway.post(f"/api/v1/models/{tabular_model['model_id']}/versions/1/promote")
    assert refused.status_code == 503, refused.text
    assert refused.json()["error"]["code"] == "DEPLOYMENT_FAILED"
    assert gateway.get(f"/api/v1/models/{tabular_model['model_id']}/production").status_code == 404

    model_id = image_model["model_id"]
    promoted = gateway.post(f"/api/v1/models/{model_id}/versions/1/promote")
    assert promoted.status_code == 200, promoted.text
    live = gateway.get(f"/api/v1/models/{model_id}/production")
    assert live.status_code == 200, live.text
    assert live.json()["version"] == 1


def test_step_11_predict(gateway, image_model):
    """POST /api/v1/predict with an image -> 200 and a prediction from the live model version."""
    response = gateway.post(
        "/api/v1/predict",
        files={"file": ("cat.png", class_image("cat"), "image/png")},
        data={"model_id": image_model["model_id"]},
    )
    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["model_id"] == image_model["model_id"]
    assert answer["version"] == 1
    assert answer["predictions"][0]["label"] == "cat", answer


def test_step_12_compute_usage_and_cost(gateway, finished_job):
    """The finished job reports gpu_hours and estimated_cost_usd from contracts/pricing.yaml.
    API part: Mariam (on). The cost page in the portal: Hilal + Adel (Tue 24 Nov)."""
    assert finished_job["started_at"] and finished_job["finished_at"], "cost needs both times"
    # The walk-through job asks for 0 GPUs and runs on the free local-cpu machine (pricing.yaml),
    # so both are 0 on a laptop; in the cloud the same fields carry the real machine's numbers.
    assert finished_job["gpu_hours"] == 0
    assert finished_job["estimated_cost_usd"] == 0
