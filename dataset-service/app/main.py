"""STAND-IN for the Datasets service (owner: Faisal). Replace it with the real service; keep the contract.

What this stand-in does: keeps datasets IN MEMORY (lost on restart), checks the file format,
computes the SHA-256 checksum and numbers the versions, exactly as
contracts/openapi/dataset-service.yaml says.
What it does NOT do (the real service must): store files in S3/MinIO, use PostgreSQL, check project
membership, record lineage and audit, return a real time-limited S3 link.
"""

import hashlib
import io
import os
import tarfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, File, Form, Header, Path, Query, UploadFile
from fastapi.responses import JSONResponse, Response

from app.common import ApiError, current_user, iso, now_utc, setup_service

SERVICE_NAME = "dataset-service"
DatasetIdPath = Annotated[str, Path(pattern=r"^dataset-[0-9]+$")]
VersionPath = Annotated[int, Path(ge=1)]
IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key", min_length=1, max_length=128)]


@dataclass
class Version:
    number: int
    data: bytes
    checksum: str
    note: str | None
    created_by: str
    created_at: datetime


@dataclass
class Dataset:
    number: int
    project_id: str
    name: str
    description: str | None
    format: str
    created_by: str
    created_at: datetime
    versions: list[Version] = field(default_factory=list)

    @property
    def dataset_id(self) -> str:
        return f"dataset-{self.number:02d}"


def matches_format(file_format: str, data: bytes) -> bool:
    """A simple check that the file really is what the uploader says it is."""
    if file_format == "csv":
        try:
            return len(data) > 0 and "," in data.decode("utf-8").splitlines()[0]
        except (UnicodeDecodeError, IndexError):
            return False
    if file_format == "zip":
        return zipfile.is_zipfile(io.BytesIO(data))
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz"):
            return True
    except (tarfile.TarError, OSError, EOFError):
        return False


def dataset_json(dataset: Dataset) -> dict:
    return {
        "dataset_id": dataset.dataset_id,
        "project_id": dataset.project_id,
        "name": dataset.name,
        "description": dataset.description,
        "format": dataset.format,
        "latest_version": len(dataset.versions),
        "created_by": dataset.created_by,
        "created_at": iso(dataset.created_at),
    }


def version_json(dataset: Dataset, version: Version) -> dict:
    return {
        "dataset_id": dataset.dataset_id,
        "version": version.number,
        "checksum_sha256": version.checksum,
        "size_bytes": len(version.data),
        "storage_uri": f"s3://datasets/{dataset.dataset_id}/v{version.number}/",
        "note": version.note,
        "created_by": version.created_by,
        "created_at": iso(version.created_at),
    }


def create_app() -> FastAPI:
    app = FastAPI(title="CloudTrain Datasets service (stand-in)", version="1.0.0")
    setup_service(app, SERVICE_NAME)
    datasets: dict[int, Dataset] = {}
    saved_answers: dict[tuple[str, str], dict] = {}  # (user, Idempotency-Key) -> first answer

    def find(dataset_id: str) -> Dataset:
        dataset = datasets.get(int(dataset_id.removeprefix("dataset-")))
        if dataset is None:
            raise ApiError(404, "DATASET_NOT_FOUND", f"Dataset {dataset_id} does not exist")
        return dataset

    def find_version(dataset_id: str, number: int) -> tuple[Dataset, Version]:
        dataset = find(dataset_id)
        if number > len(dataset.versions):
            raise ApiError(404, "DATASET_VERSION_NOT_FOUND", f"Dataset {dataset_id} has no version {number}")
        return dataset, dataset.versions[number - 1]

    async def new_version(dataset: Dataset, upload: UploadFile, note: str | None, user_id: str) -> Version:
        data = await upload.read()
        if not matches_format(dataset.format, data):
            raise ApiError(400, "INVALID_DATASET_FORMAT", f"The file is not a valid {dataset.format} file")
        version = Version(
            number=len(dataset.versions) + 1,
            data=data,
            checksum=hashlib.sha256(data).hexdigest(),
            note=note,
            created_by=user_id,
            created_at=now_utc(),
        )
        dataset.versions.append(version)
        return version

    @app.post("/datasets", status_code=201)
    async def create_dataset(
        project_id: Annotated[str, Form(pattern=r"^project-[0-9]+$")],
        name: Annotated[str, Form(min_length=1, max_length=100)],
        format: Annotated[Literal["csv", "zip", "tar_gz"], Form()],
        file: Annotated[UploadFile, File()],
        user_id: Annotated[str, Depends(current_user)],
        description: Annotated[str | None, Form(max_length=1000)] = None,
        idempotency_key: IdempotencyKey = None,
    ) -> JSONResponse:
        if idempotency_key and (user_id, idempotency_key) in saved_answers:
            return JSONResponse(status_code=201, content=saved_answers[(user_id, idempotency_key)])
        dataset = Dataset(len(datasets) + 1, project_id, name, description, format, user_id, now_utc())
        await new_version(dataset, file, None, user_id)  # checks the format before saving anything
        datasets[dataset.number] = dataset
        answer = dataset_json(dataset)
        if idempotency_key:
            saved_answers[(user_id, idempotency_key)] = answer
        return JSONResponse(status_code=201, content=answer)

    @app.get("/datasets")
    def list_datasets(
        project_id: Annotated[str, Query(pattern=r"^project-[0-9]+$")],
        user_id: Annotated[str, Depends(current_user)],
    ) -> dict:
        found = [d for d in datasets.values() if d.project_id == project_id]
        return {"items": [dataset_json(d) for d in found]}

    @app.get("/datasets/{dataset_id}")
    def get_dataset(dataset_id: DatasetIdPath, user_id: Annotated[str, Depends(current_user)]) -> dict:
        return dataset_json(find(dataset_id))

    @app.post("/datasets/{dataset_id}/versions", status_code=201)
    async def create_version(
        dataset_id: DatasetIdPath,
        file: Annotated[UploadFile, File()],
        user_id: Annotated[str, Depends(current_user)],
        note: Annotated[str | None, Form(max_length=1000)] = None,
        idempotency_key: IdempotencyKey = None,
    ) -> JSONResponse:
        if idempotency_key and (user_id, idempotency_key) in saved_answers:
            return JSONResponse(status_code=201, content=saved_answers[(user_id, idempotency_key)])
        dataset = find(dataset_id)
        answer = version_json(dataset, await new_version(dataset, file, note, user_id))
        if idempotency_key:
            saved_answers[(user_id, idempotency_key)] = answer
        return JSONResponse(status_code=201, content=answer)

    @app.get("/datasets/{dataset_id}/versions/{version}")
    def get_version(
        dataset_id: DatasetIdPath, version: VersionPath, user_id: Annotated[str, Depends(current_user)]
    ) -> dict:
        return version_json(*find_version(dataset_id, version))

    @app.get("/datasets/{dataset_id}/versions/{version}/download")
    def download(
        dataset_id: DatasetIdPath, version: VersionPath, user_id: Annotated[str, Depends(current_user)]
    ) -> Response:
        _, found = find_version(dataset_id, version)
        return Response(content=found.data, media_type="application/octet-stream")

    @app.get("/internal/datasets/{dataset_id}/versions/{version}/download-url")
    def download_url(dataset_id: DatasetIdPath, version: VersionPath) -> dict:
        dataset, found = find_version(dataset_id, version)
        # STAND-IN: not a working link. Faisal's service returns a real presigned S3 URL here.
        bucket_url = os.environ.get("S3_ENDPOINT", "http://minio:9000")
        return {
            "url": f"{bucket_url}/datasets/{dataset.dataset_id}/v{found.number}/data",
            "expires_at": iso(now_utc() + timedelta(minutes=15)),
            "checksum_sha256": found.checksum,
        }

    return app
