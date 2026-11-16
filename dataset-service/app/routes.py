"""Public and internal endpoints of the Datasets service."""

import hashlib
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Header, Path, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db import Dataset, DatasetVersion, LineageRecord
from app.errors import ApiError
from app.idempotency import create_once, fingerprint
from app.projects import ProjectsClient
from app.schemas import dataset_json, iso, version_json
from app.storage import ObjectStorage, object_key, storage_uri
from app.validation import matches_format

router = APIRouter()

DatasetIdPath = Annotated[str, Path(pattern=r"^dataset-[0-9]+$")]
VersionPath = Annotated[int, Path(ge=1)]
IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key", min_length=1, max_length=128)]
LARGEST_DATASET_NUMBER = 2**31 - 1


class LineageBody(BaseModel):
    job_id: str = Field(pattern=r"^job-[0-9]+$")


def get_session(request: Request):
    with request.app.state.sessions() as session:
        yield session


def current_user(x_user_id: Annotated[str | None, Header(max_length=128)] = None) -> str:
    if not x_user_id:
        raise ApiError(401, "NOT_AUTHENTICATED", "Missing X-User-Id (requests must come through the gateway)")
    return x_user_id


def get_storage(request: Request) -> ObjectStorage:
    return request.app.state.storage


def get_projects(request: Request) -> ProjectsClient:
    return request.app.state.projects


SessionDep = Annotated[Session, Depends(get_session)]
UserDep = Annotated[str, Depends(current_user)]
StorageDep = Annotated[ObjectStorage, Depends(get_storage)]
ProjectsDep = Annotated[ProjectsClient, Depends(get_projects)]


def load_dataset(session: Session, dataset_id: str) -> Dataset:
    number = int(dataset_id.removeprefix("dataset-"))
    dataset = (
        session.get(Dataset, number, options=(selectinload(Dataset.versions),))
        if number <= LARGEST_DATASET_NUMBER
        else None
    )
    if dataset is None:
        raise ApiError(404, "DATASET_NOT_FOUND", f"Dataset {dataset_id} does not exist")
    return dataset


def load_version(session: Session, dataset_id: str, number: int) -> tuple[Dataset, DatasetVersion]:
    dataset = load_dataset(session, dataset_id)
    version = next((item for item in dataset.versions if item.number == number), None)
    if version is None:
        raise ApiError(404, "DATASET_VERSION_NOT_FOUND", f"Dataset {dataset_id} has no version {number}")
    return dataset, version


def require_dataset_member(
    projects: ProjectsClient, dataset: Dataset, user_id: str, request: Request
) -> None:
    projects.require_member(dataset.project_id, user_id, request.state.request_id)


def add_version(
    session: Session,
    storage: ObjectStorage,
    dataset: Dataset,
    data: bytes,
    note: str | None,
    user_id: str,
) -> DatasetVersion:
    if not matches_format(dataset.format, data):
        raise ApiError(400, "INVALID_DATASET_FORMAT", f"The file is not a valid {dataset.format} file")
    number = len(dataset.versions) + 1
    # Flush first so a new dataset gets its id before we build the storage path.
    session.flush()
    dataset_id = dataset.public_id
    key = object_key(dataset_id, number)
    storage.put(key, data)
    version = DatasetVersion(
        number=number,
        checksum_sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
        storage_uri=storage_uri(dataset_id, number),
        object_key=key,
        note=note,
        created_by=user_id,
    )
    dataset.versions.append(version)
    session.flush()
    return version


@router.post("/datasets", status_code=201)
async def create_dataset(
    request: Request,
    session: SessionDep,
    storage: StorageDep,
    projects: ProjectsDep,
    user_id: UserDep,
    project_id: Annotated[str, Form(pattern=r"^project-[0-9]+$")],
    name: Annotated[str, Form(min_length=1, max_length=100)],
    format: Annotated[Literal["csv", "zip", "tar_gz"], Form()],
    file: Annotated[UploadFile, File()],
    description: Annotated[str | None, Form(max_length=1000)] = None,
    idempotency_key: IdempotencyKey = None,
) -> JSONResponse:
    projects.require_member(project_id, user_id, request.state.request_id)
    data = await file.read()
    checksum = hashlib.sha256(data).hexdigest()

    def create() -> tuple[int, dict]:
        dataset = Dataset(
            project_id=project_id,
            name=name,
            description=description,
            format=format,
            created_by=user_id,
        )
        session.add(dataset)
        add_version(session, storage, dataset, data, None, user_id)
        return 201, dataset_json(dataset)

    request_fingerprint = fingerprint(
        "POST",
        "/datasets",
        {
            "project_id": project_id,
            "name": name,
            "description": description,
            "format": format,
            "checksum": checksum,
        },
    )
    status_code, answer = create_once(session, user_id, idempotency_key, request_fingerprint, create)
    return JSONResponse(status_code=status_code, content=answer)


@router.get("/datasets")
def list_datasets(
    request: Request,
    session: SessionDep,
    projects: ProjectsDep,
    user_id: UserDep,
    project_id: Annotated[str, Query(pattern=r"^project-[0-9]+$")],
) -> dict:
    projects.require_member(project_id, user_id, request.state.request_id)
    query = (
        select(Dataset)
        .where(Dataset.project_id == project_id)
        .options(selectinload(Dataset.versions))
        .order_by(Dataset.id)
    )
    return {"items": [dataset_json(dataset) for dataset in session.scalars(query)]}


@router.get("/datasets/{dataset_id}")
def get_dataset(
    request: Request, dataset_id: DatasetIdPath, session: SessionDep, projects: ProjectsDep, user_id: UserDep
) -> dict:
    dataset = load_dataset(session, dataset_id)
    require_dataset_member(projects, dataset, user_id, request)
    return dataset_json(dataset)


@router.post("/datasets/{dataset_id}/versions", status_code=201)
async def create_version(
    request: Request,
    dataset_id: DatasetIdPath,
    session: SessionDep,
    storage: StorageDep,
    projects: ProjectsDep,
    user_id: UserDep,
    file: Annotated[UploadFile, File()],
    note: Annotated[str | None, Form(max_length=1000)] = None,
    idempotency_key: IdempotencyKey = None,
) -> JSONResponse:
    data = await file.read()
    checksum = hashlib.sha256(data).hexdigest()

    def create() -> tuple[int, dict]:
        dataset = load_dataset(session, dataset_id)
        require_dataset_member(projects, dataset, user_id, request)
        version = add_version(session, storage, dataset, data, note, user_id)
        return 201, version_json(dataset, version)

    request_fingerprint = fingerprint(
        "POST",
        f"/datasets/{dataset_id}/versions",
        {"note": note, "checksum": checksum},
    )
    status_code, answer = create_once(session, user_id, idempotency_key, request_fingerprint, create)
    return JSONResponse(status_code=status_code, content=answer)


@router.get("/datasets/{dataset_id}/versions/{version}")
def get_version(
    request: Request,
    dataset_id: DatasetIdPath,
    version: VersionPath,
    session: SessionDep,
    projects: ProjectsDep,
    user_id: UserDep,
) -> dict:
    dataset, found = load_version(session, dataset_id, version)
    require_dataset_member(projects, dataset, user_id, request)
    return version_json(dataset, found)


@router.get("/datasets/{dataset_id}/versions/{version}/download")
def download(
    request: Request,
    dataset_id: DatasetIdPath,
    version: VersionPath,
    session: SessionDep,
    storage: StorageDep,
    projects: ProjectsDep,
    user_id: UserDep,
) -> Response:
    dataset, found = load_version(session, dataset_id, version)
    require_dataset_member(projects, dataset, user_id, request)
    return Response(content=storage.get(found.object_key), media_type="application/octet-stream")


@router.get("/internal/datasets/{dataset_id}/versions/{version}/download-url")
def download_url(
    dataset_id: DatasetIdPath, version: VersionPath, session: SessionDep, storage: StorageDep
) -> dict:
    _, found = load_version(session, dataset_id, version)
    link = storage.presigned_get(found.object_key)
    return {
        "url": link.url,
        "expires_at": iso(link.expires_at),
        "checksum_sha256": found.checksum_sha256,
    }


@router.post("/internal/datasets/{dataset_id}/versions/{version}/lineage", status_code=201)
def record_lineage(
    dataset_id: DatasetIdPath, version: VersionPath, body: LineageBody, session: SessionDep
) -> dict:
    """Record that a training job used this dataset version."""
    dataset, found = load_version(session, dataset_id, version)
    existing = session.scalars(
        select(LineageRecord).where(
            LineageRecord.dataset_id == dataset.id,
            LineageRecord.version == found.number,
            LineageRecord.job_id == body.job_id,
        )
    ).first()
    if existing is None:
        existing = LineageRecord(dataset_id=dataset.id, version=found.number, job_id=body.job_id)
        session.add(existing)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            existing = session.scalars(
                select(LineageRecord).where(
                    LineageRecord.dataset_id == dataset.id,
                    LineageRecord.version == found.number,
                    LineageRecord.job_id == body.job_id,
                )
            ).one()
    return {
        "dataset_id": dataset.public_id,
        "version": found.number,
        "job_id": body.job_id,
        "recorded_at": iso(existing.recorded_at),
    }


@router.get("/internal/datasets/{dataset_id}/versions/{version}/lineage")
def list_lineage(dataset_id: DatasetIdPath, version: VersionPath, session: SessionDep) -> dict:
    dataset, found = load_version(session, dataset_id, version)
    rows = session.scalars(
        select(LineageRecord)
        .where(LineageRecord.dataset_id == dataset.id, LineageRecord.version == found.number)
        .order_by(LineageRecord.recorded_at)
    )
    return {
        "items": [
            {
                "dataset_id": dataset.public_id,
                "version": row.version,
                "job_id": row.job_id,
                "recorded_at": iso(row.recorded_at),
            }
            for row in rows
        ]
    }
