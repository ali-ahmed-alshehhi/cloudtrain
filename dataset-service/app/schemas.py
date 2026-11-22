"""JSON shapes returned by the Datasets API (must match contracts/openapi/dataset-service.yaml)."""

from datetime import UTC, datetime

from app.db import Dataset, DatasetVersion


def iso(moment: datetime) -> str:
    # All times are stored in UTC; a database that drops the zone (SQLite in tests) gives them back naive.
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def dataset_json(dataset: Dataset) -> dict:
    return {
        "dataset_id": dataset.public_id,
        "project_id": dataset.project_id,
        "name": dataset.name,
        "description": dataset.description,
        "format": dataset.format,
        "latest_version": dataset.latest_version,
        "created_by": dataset.created_by,
        "created_at": iso(dataset.created_at),
    }


def version_json(dataset: Dataset, version: DatasetVersion) -> dict:
    return {
        "dataset_id": dataset.public_id,
        "version": version.number,
        "checksum_sha256": version.checksum_sha256,
        "size_bytes": version.size_bytes,
        "storage_uri": version.storage_uri,
        "note": version.note,
        "created_by": version.created_by,
        "created_at": iso(version.created_at),
    }
