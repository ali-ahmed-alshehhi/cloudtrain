"""The Datasets stand-in answers as the contract says. Keep these tests passing when you replace it."""

import hashlib
import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import USER

CSV = b"age,income,label\n31,42000,1\n"


@pytest.fixture
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


def upload(client, data=CSV, file_format="csv", headers=USER):
    return client.post(
        "/datasets",
        data={"project_id": "project-01", "name": "customers", "format": file_format},
        files={"file": ("data", data, "application/octet-stream")},
        headers=headers,
    )


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "service": "dataset-service"}


def test_upload_creates_version_1_with_a_checksum(client, check):
    response = upload(client)

    assert response.status_code == 201
    check(response.json(), "Dataset")
    dataset_id = response.json()["dataset_id"]
    version = client.get(f"/datasets/{dataset_id}/versions/1", headers=USER).json()
    check(version, "DatasetVersion")
    assert version["checksum_sha256"] == hashlib.sha256(CSV).hexdigest()


def test_zip_upload_and_new_version(client, check):
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("cat/1.png", b"fake image")
    dataset_id = upload(client, archive.getvalue(), "zip").json()["dataset_id"]

    response = client.post(
        f"/datasets/{dataset_id}/versions", files={"file": ("v2.zip", archive.getvalue())}, headers=USER
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
    check(response.json(), "DownloadUrl")
