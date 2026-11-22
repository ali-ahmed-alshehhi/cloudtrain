"""Datasets service answers as the contract says, with files in object storage."""

import hashlib
import io
import tarfile
import zipfile

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.main import create_app
from app.storage import MemoryStorage
from tests.conftest import STRANGER, USER

CSV = b"age,income,label\n31,42000,1\n"
CSV_V2 = b"age,income,label\n40,55000,0\n"


def upload(client, data=CSV, file_format="csv", headers=USER, project_id="project-01"):
    return client.post(
        "/datasets",
        data={"project_id": project_id, "name": "customers", "format": file_format},
        files={"file": ("data", data, "application/octet-stream")},
        headers=headers,
    )


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "service": "dataset-service"}


def test_upload_creates_version_1_with_a_checksum(client, check, storage):
    response = upload(client)

    assert response.status_code == 201
    check(response.json(), "Dataset")
    dataset_id = response.json()["dataset_id"]
    version = client.get(f"/datasets/{dataset_id}/versions/1", headers=USER).json()
    check(version, "DatasetVersion")
    assert version["checksum_sha256"] == hashlib.sha256(CSV).hexdigest()
    assert version["storage_uri"] == f"s3://datasets/{dataset_id}/v1/"
    assert storage.get(f"{dataset_id}/v1/data") == CSV


def test_zip_upload_and_new_version(client, check):
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("cat/1.png", b"fake image")
    payload = archive.getvalue()
    dataset_id = upload(client, payload, "zip").json()["dataset_id"]

    response = client.post(
        f"/datasets/{dataset_id}/versions", files={"file": ("v2.zip", payload)}, headers=USER
    )

    assert response.status_code == 201
    check(response.json(), "DatasetVersion")
    assert response.json()["version"] == 2


def test_wrong_format_is_400(client, check):
    response = upload(client, b"not a zip", "zip")

    assert response.status_code == 400
    check(response.json(), "Error")


def test_without_login_is_401(client):
    assert upload(client, headers={}).status_code == 401


def test_missing_version_is_404(client, check):
    dataset_id = upload(client).json()["dataset_id"]

    response = client.get(f"/datasets/{dataset_id}/versions/9", headers=USER)

    assert response.status_code == 404
    check(response.json(), "Error")


def test_list_and_download(client, check):
    dataset_id = upload(client).json()["dataset_id"]

    listed = client.get("/datasets?project_id=project-01", headers=USER).json()
    check(listed, "DatasetList")
    assert client.get(f"/datasets/{dataset_id}/versions/1/download", headers=USER).content == CSV


def test_internal_download_url(client, check):
    dataset_id = upload(client).json()["dataset_id"]

    response = client.get(f"/internal/datasets/{dataset_id}/versions/1/download-url")

    assert response.status_code == 200
    body = response.json()
    check(body, "DownloadUrl")
    assert body["url"].startswith("memory://")
    assert body["checksum_sha256"] == hashlib.sha256(CSV).hexdigest()


def test_idempotent_upload(client):
    headers = {**USER, "Idempotency-Key": "upload-1"}
    first = upload(client, headers=headers)
    second = upload(client, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json() == second.json()


def test_storage_down_is_503(client, check, storage):
    storage.fail = True

    response = upload(client)

    assert response.status_code == 503
    check(response.json(), "Error")
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


def test_download_url_missing_dataset_is_404(client, check):
    response = client.get("/internal/datasets/dataset-99/versions/1/download-url")

    assert response.status_code == 404
    check(response.json(), "Error")


def test_download_url_missing_version_is_404(client, check):
    dataset_id = upload(client).json()["dataset_id"]

    response = client.get(f"/internal/datasets/{dataset_id}/versions/9/download-url")

    assert response.status_code == 404
    check(response.json(), "Error")


def test_idempotency_key_reused_with_different_file_is_409(client, check):
    headers = {**USER, "Idempotency-Key": "same-key"}
    assert upload(client, CSV, headers=headers).status_code == 201

    response = upload(client, CSV_V2, headers=headers)

    assert response.status_code == 409
    check(response.json(), "Error")
    assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_non_member_cannot_see_dataset(client, check):
    dataset_id = upload(client).json()["dataset_id"]

    response = client.get(f"/datasets/{dataset_id}", headers=STRANGER)

    assert response.status_code == 403
    check(response.json(), "Error")
    assert response.json()["error"]["code"] == "NOT_A_MEMBER"


def test_non_member_cannot_list_or_upload(client, check):
    assert upload(client, headers=STRANGER).status_code == 403
    listed = client.get("/datasets?project_id=project-01", headers=STRANGER)
    assert listed.status_code == 403
    check(listed.json(), "Error")


def test_lineage_records_which_job_used_a_version(client):
    dataset_id = upload(client).json()["dataset_id"]

    created = client.post(f"/internal/datasets/{dataset_id}/versions/1/lineage", json={"job_id": "job-04"})
    listed = client.get(f"/internal/datasets/{dataset_id}/versions/1/lineage")

    assert created.status_code == 201
    assert created.json()["job_id"] == "job-04"
    assert listed.status_code == 200
    assert listed.json()["items"][0]["job_id"] == "job-04"


def audit_actions(client, dataset_id):
    response = client.get(f"/internal/datasets/{dataset_id}/audit")
    assert response.status_code == 200
    return [(item["action"], item["version"], item["actor"]) for item in response.json()["items"]]


def test_audit_records_uploads_and_downloads(client):
    dataset_id = upload(client).json()["dataset_id"]
    client.post(f"/datasets/{dataset_id}/versions", files={"file": ("v2.csv", CSV_V2)}, headers=USER)
    client.get(f"/datasets/{dataset_id}/versions/2/download", headers=USER)
    client.get(f"/internal/datasets/{dataset_id}/versions/1/download-url")

    assert audit_actions(client, dataset_id) == [
        ("upload", 1, "user-1"),
        ("new_version", 2, "user-1"),
        ("download", 2, "user-1"),
        ("download_url", 1, "internal"),
    ]


def test_audit_keeps_the_request_id(client):
    dataset_id = upload(client, headers={**USER, "X-Request-Id": "req-audit-1"}).json()["dataset_id"]

    item = client.get(f"/internal/datasets/{dataset_id}/audit").json()["items"][0]

    assert item["request_id"] == "req-audit-1"
    assert item["at"].endswith("Z")


def test_repeated_upload_with_same_key_is_audited_once(client):
    headers = {**USER, "Idempotency-Key": "audit-once"}
    dataset_id = upload(client, headers=headers).json()["dataset_id"]
    upload(client, headers=headers)

    assert audit_actions(client, dataset_id) == [("upload", 1, "user-1")]


def test_refused_download_is_not_audited(client):
    dataset_id = upload(client).json()["dataset_id"]

    assert client.get(f"/datasets/{dataset_id}/versions/1/download", headers=STRANGER).status_code == 403
    assert audit_actions(client, dataset_id) == [("upload", 1, "user-1")]


def test_failed_new_version_is_not_audited(client, storage):
    dataset_id = upload(client).json()["dataset_id"]
    storage.fail = True

    response = client.post(
        f"/datasets/{dataset_id}/versions", files={"file": ("v2.csv", CSV_V2)}, headers=USER
    )

    assert response.status_code == 503
    storage.fail = False
    assert audit_actions(client, dataset_id) == [("upload", 1, "user-1")]


def test_audit_of_missing_dataset_is_404(client, check):
    response = client.get("/internal/datasets/dataset-99/audit")

    assert response.status_code == 404
    check(response.json(), "Error")


def test_storage_uri_uses_the_real_bucket_name(engine, projects):
    cloud_storage = MemoryStorage(bucket="cloudtrain-dev-datasets-abc123")
    with TestClient(create_app(engine, cloud_storage, projects)) as cloud_client:
        dataset_id = upload(cloud_client).json()["dataset_id"]
        version = cloud_client.get(f"/datasets/{dataset_id}/versions/1", headers=USER).json()

    assert version["storage_uri"] == f"s3://cloudtrain-dev-datasets-abc123/{dataset_id}/v1/"


def test_get_dataset_as_member(client, check):
    dataset_id = upload(client).json()["dataset_id"]

    response = client.get(f"/datasets/{dataset_id}", headers=USER)

    assert response.status_code == 200
    check(response.json(), "Dataset")
    assert response.json()["latest_version"] == 1


def test_tar_gz_upload(client):
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w:gz") as packed:
        content = b"label\n1\n"
        member = tarfile.TarInfo("train.csv")
        member.size = len(content)
        packed.addfile(member, io.BytesIO(content))

    response = upload(client, archive.getvalue(), "tar_gz")

    assert response.status_code == 201
    assert response.json()["format"] == "tar_gz"


def test_non_member_cannot_add_a_version(client, check):
    dataset_id = upload(client).json()["dataset_id"]

    response = client.post(
        f"/datasets/{dataset_id}/versions", files={"file": ("v2.csv", CSV_V2)}, headers=STRANGER
    )

    assert response.status_code == 403
    check(response.json(), "Error")
    assert client.get(f"/datasets/{dataset_id}", headers=USER).json()["latest_version"] == 1


def test_unknown_project_is_404(client, check):
    response = upload(client, project_id="project-77")

    assert response.status_code == 404
    check(response.json(), "Error")
    assert response.json()["error"]["code"] == "PROJECT_NOT_FOUND"


def test_download_url_when_storage_is_down_is_503(client, check, storage):
    dataset_id = upload(client).json()["dataset_id"]
    storage.fail = True

    response = client.get(f"/internal/datasets/{dataset_id}/versions/1/download-url")

    assert response.status_code == 503
    check(response.json(), "Error")


def test_same_job_is_recorded_once_in_lineage(client):
    dataset_id = upload(client).json()["dataset_id"]
    path = f"/internal/datasets/{dataset_id}/versions/1/lineage"

    first = client.post(path, json={"job_id": "job-04"})
    second = client.post(path, json={"job_id": "job-04"})

    assert first.json() == second.json()
    assert len(client.get(path).json()["items"]) == 1


def test_bad_job_id_in_lineage_is_422(client):
    dataset_id = upload(client).json()["dataset_id"]

    response = client.post(f"/internal/datasets/{dataset_id}/versions/1/lineage", json={"job_id": "oops"})

    assert response.status_code == 422


def test_health_when_database_is_down_is_503(storage, projects, check):
    broken = create_engine("sqlite:////nonexistent-folder/datasets.db")
    with TestClient(create_app(broken, storage, projects)) as broken_client:
        response = broken_client.get("/health")

    assert response.status_code == 503
    check(response.json(), "Error")


def test_missing_file_in_storage_is_404_not_503(client, check, storage):
    dataset_id = upload(client).json()["dataset_id"]
    storage.objects.clear()  # what a LocalStack restart does: the record stays, the file is gone

    response = client.get(f"/datasets/{dataset_id}/versions/1/download", headers=USER)

    assert response.status_code == 404
    check(response.json(), "Error")
    assert response.json()["error"]["code"] == "DATASET_FILE_MISSING"
    assert audit_actions(client, dataset_id) == [("upload", 1, "user-1")]
