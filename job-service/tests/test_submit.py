"""POST /jobs: checks, membership, dataset version, idempotency, and the queue message."""

import httpx

from tests.conftest import FORM, OTHER, USER, fake_services, submit


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "service": "job-service"}


def test_health_is_503_when_the_queue_is_down(client, queues, check):
    queues.down = True
    response = client.get("/health")
    assert response.status_code == 503
    check(response.json(), "Error")


def test_submit_answers_202_and_queues_the_full_form(client, queues, check):
    job = submit(client)

    check(job, "Job")
    assert job["status"] == "QUEUED"
    assert job["attempt"] == 1
    [message] = queues.sent["training-jobs"]
    check(message, "training-job.schema.json")  # the queue carries the shared job form
    assert message["job_id"] == job["job_id"]
    assert queues.types() == ["job.queued"]


def test_job_ids_follow_the_naming_rule(client):
    assert [submit(client)["job_id"] for _ in range(2)] == ["job-01", "job-02"]


def test_ddp_world_size_must_match_gpu_count(client, check):
    form = {**FORM, "parallelism": {"strategy": "ddp", "world_size": 4}}

    response = client.post("/jobs", json=form, headers=USER)

    assert response.status_code == 422
    check(response.json(), "Error")


def test_unknown_field_is_422(client):
    assert client.post("/jobs", json={**FORM, "priority": "high"}, headers=USER).status_code == 422


def test_missing_dataset_version_is_404(client, queues):
    response = client.post("/jobs", json={**FORM, "dataset_version": 7}, headers=USER)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DATASET_VERSION_NOT_FOUND"
    assert queues.sent["training-jobs"] == []


def test_dataset_of_another_project_is_refused(client, queues):
    response = client.post("/jobs", json={**FORM, "dataset_id": "dataset-02"}, headers=USER)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "DATASET_NOT_IN_PROJECT"
    assert queues.sent["training-jobs"] == []


def test_only_project_members_can_submit(client, queues):
    response = client.post("/jobs", json=FORM, headers=OTHER)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NOT_A_MEMBER"
    assert queues.sent["training-jobs"] == []


def test_unknown_project_is_404(client):
    response = client.post("/jobs", json={**FORM, "project_id": "project-99"}, headers=USER)
    assert response.json()["error"]["code"] == "PROJECT_NOT_FOUND"


def test_without_login_is_401(client):
    assert client.post("/jobs", json=FORM).status_code == 401


def test_datasets_service_down_is_503(make_client, check):
    def datasets_refuse(request):
        if request.url.path.startswith("/datasets"):
            raise httpx.ConnectError("refused", request=request)
        return fake_services(request)

    with make_client(httpx.MockTransport(datasets_refuse)) as client:
        response = client.post("/jobs", json=FORM, headers=USER)

    assert response.status_code == 503
    check(response.json(), "Error")


def test_projects_service_down_is_503(make_client):
    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    with make_client(httpx.MockTransport(refuse)) as client:
        assert client.post("/jobs", json=FORM, headers=USER).status_code == 503


def test_same_idempotency_key_queues_only_once(client, queues):
    headers = {**USER, "Idempotency-Key": "submit-1"}

    first = submit(client, headers=headers)
    second = submit(client, headers=headers)

    assert first == second
    assert len(queues.sent["training-jobs"]) == 1


def test_same_key_for_a_different_job_is_409(client):
    headers = {**USER, "Idempotency-Key": "submit-1"}
    submit(client, headers=headers)

    response = client.post("/jobs", json={**FORM, "model": "resnet50"}, headers=headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_queue_down_still_accepts_and_sends_later(client, queues):
    """The outbox: the job is saved with its message, and the message goes out when SQS is back."""
    from tests.conftest import sweep

    queues.down = True
    job = submit(client)
    assert job["status"] == "QUEUED"
    assert queues.sent["training-jobs"] == []

    queues.down = False
    sweep(client)

    assert [m["job_id"] for m in queues.sent["training-jobs"]] == [job["job_id"]]
    assert queues.types() == ["job.queued"]


def test_a_job_survives_a_restart(make_client, client):
    job_id = submit(client)["job_id"]

    with make_client() as restarted:  # a new app on the same database
        assert restarted.get(f"/jobs/{job_id}", headers=USER).json()["status"] == "QUEUED"
