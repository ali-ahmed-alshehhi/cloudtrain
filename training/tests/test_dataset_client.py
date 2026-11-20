import hashlib
import io
import zipfile

import httpx
import pytest

from app.dataset import DatasetClient, DatasetError


def zip_bytes(name: str = "cifar-10-batches-py/data.txt", content: bytes = b"training data") -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(name, content)
    return output.getvalue()


def test_download_verifies_and_safely_extracts_dataset(tmp_path):
    payload = zip_bytes()

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/download-url"):
            return httpx.Response(
                200,
                json={
                    "url": "https://objects.test/dataset.zip",
                    "checksum_sha256": hashlib.sha256(payload).hexdigest(),
                },
            )
        return httpx.Response(200, content=payload)

    client = DatasetClient(
        httpx.Client(transport=httpx.MockTransport(handle)),
        "http://dataset-service:8002",
        tmp_path,
    )

    downloaded = client.download("dataset-01", 1)

    assert (downloaded / "cifar-10-batches-py/data.txt").read_bytes() == b"training data"


def test_checksum_mismatch_fails_clearly(tmp_path):
    payload = zip_bytes()

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/download-url"):
            return httpx.Response(
                200,
                json={"url": "https://objects.test/dataset.zip", "checksum_sha256": "0" * 64},
            )
        return httpx.Response(200, content=payload)

    client = DatasetClient(
        httpx.Client(transport=httpx.MockTransport(handle)),
        "http://dataset-service:8002",
        tmp_path,
    )

    with pytest.raises(DatasetError, match="checksum"):
        client.download("dataset-01", 1)


def test_archive_path_traversal_is_rejected(tmp_path):
    payload = zip_bytes("../../escape.txt")

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/download-url"):
            return httpx.Response(
                200,
                json={
                    "url": "https://objects.test/dataset.zip",
                    "checksum_sha256": hashlib.sha256(payload).hexdigest(),
                },
            )
        return httpx.Response(200, content=payload)

    client = DatasetClient(
        httpx.Client(transport=httpx.MockTransport(handle)),
        "http://dataset-service:8002",
        tmp_path,
    )

    with pytest.raises(DatasetError, match="unsafe"):
        client.download("dataset-01", 1)
    assert not (tmp_path / "escape.txt").exists()


def test_single_csv_file_is_extracted(tmp_path):
    csv_bytes = b"radius,texture,diagnosis\n1.0,1.1,B\n8.0,8.1,M\n"
    digest = hashlib.sha256(csv_bytes).hexdigest()

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/download-url"):
            return httpx.Response(
                200,
                json={
                    "url": "http://datasets.test/file",
                    "expires_at": "2026-11-15T00:00:00Z",
                    "checksum_sha256": digest,
                },
            )
        return httpx.Response(200, content=csv_bytes)

    client = DatasetClient(
        httpx.Client(transport=httpx.MockTransport(handle)),
        "http://dataset-service.test",
        storage_root=tmp_path,
    )
    extracted = client.download("dataset-01", 1)
    assert (extracted / "dataset.csv").read_bytes() == csv_bytes
    client.cleanup(extracted)
