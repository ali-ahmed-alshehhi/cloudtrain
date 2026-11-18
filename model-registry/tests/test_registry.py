"""The Model Registry: register from MLflow, promote and roll back behind the health gate."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common import iso
from app.db import Deployment, Release
from tests.conftest import ALICE, BOB, registration


def register(client, run_id="run-a", **changes) -> dict:
    response = client.post("/models", json=registration(run_id, **changes), headers=ALICE)
    assert response.status_code == 201, response.text
    return response.json()


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "service": "model-registry"}


def test_register_reads_the_run_from_mlflow(client, services, check):
    version = register(client)

    check(version, "ModelVersion")
    assert version["model_id"] == "model-01"
    assert version["version"] == 1
    assert version["metrics"] == {"accuracy": 0.91}  # NaN dropped: JSON cannot hold it
    assert version["stage"] == "none"
    assert version["artifact_uri"] == "s3://artifacts/mlflow/1/models/m-run-a/artifacts"
    mlflow_version = services.registered["model-01"][0]
    assert mlflow_version["run_id"] == "run-a"
    assert mlflow_version["model_id"] == "m-run-a"
    tags = {tag["key"]: tag["value"] for tag in mlflow_version["tags"]}
    assert (
        tags["job_id"] == "job-01" and tags["dataset_id"] == "dataset-01" and tags["dataset_version"] == "1"
    )


def test_second_registration_adds_a_version(client, check):
    register(client)
    second = register(client, "run-b")

    assert second["model_id"] == "model-01" and second["version"] == 2
    listed = client.get("/models", headers=ALICE).json()
    check(listed, "ModelList")
    assert listed["items"][0]["latest_version"] == 2
    assert listed["items"][0]["production_version"] is None


def test_mlflow2_run_with_model_in_its_artifacts(client, services):
    services.add_run("run-old", mlflow3=False)

    version = register(client, "run-old")

    assert version["artifact_uri"] == "s3://artifacts/mlflow/1/run-old/artifacts/model"


def test_unknown_run_is_400(client, check):
    response = client.post("/models", json=registration("no-such-run"), headers=ALICE)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "RUN_NOT_FOUND"
    check(response.json(), "Error")


def test_run_without_a_model_is_400(client, services):
    services.add_run("run-empty", mlflow3=False)
    services.no_model.add("run-empty")

    response = client.post("/models", json=registration("run-empty"), headers=ALICE)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "MODEL_NOT_IN_RUN"


def test_unfinished_run_is_400(client, services):
    services.add_run("run-live", status="RUNNING")

    response = client.post("/models", json=registration("run-live"), headers=ALICE)

    assert response.json()["error"]["code"] == "RUN_NOT_FINISHED"


def test_run_of_another_job_is_400(client, services):
    services.add_run("run-other", tags={"job_id": "job-77"})

    response = client.post("/models", json=registration("run-other"), headers=ALICE)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "RUN_MISMATCH"


def test_same_run_twice_is_409(client):
    register(client)

    response = client.post("/models", json=registration(), headers=ALICE)

    assert response.status_code == 409


def test_idempotency_key_returns_the_first_answer(client, services):
    headers = {**ALICE, "Idempotency-Key": "abc"}
    first = client.post("/models", json=registration(), headers=headers)
    again = client.post("/models", json=registration(), headers=headers)
    other = client.post("/models", json=registration("run-b"), headers=headers)

    assert first.status_code == again.status_code == 201
    assert first.json() == again.json()
    assert len(services.registered["model-01"]) == 1
    assert other.status_code == 409


def test_mlflow_down_is_503(client, services):
    services.mlflow_down = True

    response = client.post("/models", json=registration(), headers=ALICE)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "MLFLOW_UNAVAILABLE"


def test_only_members_can_register_or_see(client, check):
    not_member = client.post("/models", json=registration(), headers=BOB)
    register(client)

    assert not_member.status_code == 403
    check(not_member.json(), "Error")
    assert client.get("/models", headers=BOB).json() == {"items": []}
    assert client.get("/models", params={"project_id": "project-01"}, headers=BOB).status_code == 403
    assert client.get("/models/model-01/versions", headers=BOB).status_code == 403
    assert client.post("/models/model-01/versions/1/promote", headers=BOB).status_code == 403


def test_unknown_project_is_404(client):
    response = client.post("/models", json=registration(project_id="project-99"), headers=ALICE)

    assert response.status_code == 404
    assert client.get("/models", params={"project_id": "project-99"}, headers=ALICE).json() == {"items": []}


def test_promote_passes_the_health_gate_then_goes_live(client, services, check):
    register(client)
    assert client.get("/models/model-01/production").status_code == 404  # nothing live yet

    live = client.post("/models/model-01/versions/1/promote", headers=ALICE)

    assert live.status_code == 200, live.text
    check(live.json(), "Production")
    assert live.json()["version"] == 1
    assert services.candidates == [
        (
            "model-01",
            {
                "name": "resnet18-cifar10",
                "version": 1,
                "mlflow_run_id": "run-a",
                "artifact_uri": "s3://artifacts/mlflow/1/models/m-run-a/artifacts",
            },
        )
    ]
    assert services.aliases == {"model-01": "1"}
    assert services.switches == ["model-01"]
    assert client.get("/models/model-01/production").json() == live.json()


def test_failed_deployment_never_replaces_the_healthy_version(client, services, engine):
    register(client)
    register(client, "run-b")
    client.post("/models/model-01/versions/1/promote", headers=ALICE)
    services.unhealthy.add(("model-01", 2))

    response = client.post("/models/model-01/versions/2/promote", headers=ALICE)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DEPLOYMENT_FAILED"
    assert "version 1 stays live" in response.json()["error"]["message"]
    assert client.get("/models/model-01/production").json()["version"] == 1
    assert services.aliases == {"model-01": "1"}
    stages = [v["stage"] for v in client.get("/models/model-01/versions", headers=ALICE).json()["items"]]
    assert stages == ["production", "none"]
    with Session(engine) as session:
        attempts = [
            (d.version, d.status) for d in session.scalars(select(Deployment).order_by(Deployment.id))
        ]
    assert attempts == [(1, "succeeded"), (2, "failed")]


def test_inference_down_blocks_the_deployment(client, services):
    register(client)
    services.inference_down = True

    response = client.post("/models/model-01/versions/1/promote", headers=ALICE)

    assert response.status_code == 503
    assert client.get("/models/model-01/production").status_code == 404


def test_rollback_goes_back_to_the_previous_live_version(client, services, check):
    register(client)
    register(client, "run-b")
    client.post("/models/model-01/versions/1/promote", headers=ALICE)
    client.post("/models/model-01/versions/2/promote", headers=ALICE)

    rolled_back = client.post("/models/model-01/rollback", headers=ALICE)

    assert rolled_back.status_code == 200
    check(rolled_back.json(), "Production")
    assert rolled_back.json()["version"] == 1
    assert client.get("/models/model-01/production").json()["version"] == 1
    assert services.aliases == {"model-01": "1"}
    versions = client.get("/models/model-01/versions", headers=ALICE).json()
    check(versions, "ModelVersionList")
    assert [v["stage"] for v in versions["items"]] == ["production", "archived"]


def test_rollback_target_must_also_be_healthy(client, services):
    register(client)
    register(client, "run-b")
    client.post("/models/model-01/versions/1/promote", headers=ALICE)
    client.post("/models/model-01/versions/2/promote", headers=ALICE)
    services.unhealthy.add(("model-01", 1))

    response = client.post("/models/model-01/rollback", headers=ALICE)

    assert response.status_code == 503
    assert client.get("/models/model-01/production").json()["version"] == 2


def test_rollback_with_nothing_before_is_409(client, check):
    register(client)
    client.post("/models/model-01/versions/1/promote", headers=ALICE)

    response = client.post("/models/model-01/rollback", headers=ALICE)

    assert response.status_code == 409
    check(response.json(), "Error")


def test_promoting_the_live_version_again_changes_nothing(client, services):
    register(client)
    client.post("/models/model-01/versions/1/promote", headers=ALICE)

    again = client.post("/models/model-01/versions/1/promote", headers=ALICE)

    assert again.status_code == 200
    assert len(services.candidates) == 1


def test_unknown_model_or_version_is_404(client):
    register(client)

    assert client.get("/models/model-99/versions", headers=ALICE).status_code == 404
    assert client.get("/models/model-99999999999/production").status_code == 404
    assert client.post("/models/model-01/versions/5/promote", headers=ALICE).status_code == 404


def test_without_login_is_401(client):
    assert client.get("/models").status_code == 401
    assert client.post("/models", json=registration()).status_code == 401


def test_naive_database_times_are_utc_whatever_the_machine_clock(dubai_time):
    assert iso(datetime(2026, 11, 16, 12)) == "2026-11-16T12:00:00Z"
    assert iso(datetime(2026, 11, 16, 12, tzinfo=UTC)) == "2026-11-16T12:00:00Z"


def test_promoted_at_reads_back_unchanged_whatever_the_machine_clock(client, engine, dubai_time):
    register(client)
    promoted = client.post("/models/model-01/versions/1/promote", headers=ALICE).json()

    with Session(engine) as session:
        stored = session.scalars(select(Release)).one().promoted_at

    assert client.get("/models/model-01/production").json()["promoted_at"] == promoted["promoted_at"]
    assert promoted["promoted_at"] == stored.isoformat() + "Z"  # SQLite gives the UTC time back naive
