"""Datasets service answers as the contract says, with files in object storage."""

import hashlib
import io
import zipfile

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
