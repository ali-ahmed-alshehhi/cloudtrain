"""Object storage for dataset files: LocalStack S3 locally, real S3 in the cloud.

Object key layout: `<dataset_id>/v<version>/data` inside the datasets bucket
(shown outside as `s3://<bucket>/<dataset_id>/v<version>/`). The bucket is `datasets` locally; on AWS
it has a globally unique name (DATASETS_BUCKET), so the URI always uses the real bucket name.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError, EndpointConnectionError


class StorageUnavailable(Exception):
    """Raised when object storage cannot be reached or fails a read/write."""


def storage_uri(bucket: str, dataset_id: str, version: int) -> str:
    return f"s3://{bucket}/{dataset_id}/v{version}/"


def object_key(dataset_id: str, version: int) -> str:
    return f"{dataset_id}/v{version}/data"


@dataclass
class PresignedDownload:
    url: str
    expires_at: datetime


class ObjectStorage(Protocol):
    bucket: str

    def put(self, key: str, data: bytes) -> None: ...

    def get(self, key: str) -> bytes: ...

    def presigned_get(self, key: str, expires_seconds: int = 900) -> PresignedDownload: ...


@dataclass
class MemoryStorage:
    """In-memory stand-in used by unit tests (no LocalStack needed)."""

    objects: dict[str, bytes] = field(default_factory=dict)
    fail: bool = False
    bucket: str = "datasets"

    def _maybe_fail(self) -> None:
        if self.fail:
            raise StorageUnavailable("Object storage is not reachable")

    def put(self, key: str, data: bytes) -> None:
        self._maybe_fail()
        self.objects[key] = data

    def get(self, key: str) -> bytes:
        self._maybe_fail()
        return self.objects[key]

    def presigned_get(self, key: str, expires_seconds: int = 900) -> PresignedDownload:
        self._maybe_fail()
        if key not in self.objects:
            raise KeyError(key)
        return PresignedDownload(
            url=f"memory://{key}",
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_seconds),
        )


class S3Storage:
    def __init__(
        self,
        bucket: str | None = None,
        endpoint_url: str | None = None,
        region: str | None = None,
    ) -> None:
        self.bucket = bucket or os.environ.get("DATASETS_BUCKET", "datasets")
        endpoint = endpoint_url if endpoint_url is not None else os.environ.get("S3_ENDPOINT")
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint or None,
            region_name=region or os.environ.get("AWS_REGION", "us-east-1"),
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
            config=Config(signature_version="s3v4"),
        )

    def put(self, key: str, data: bytes) -> None:
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=data)
        except (ClientError, EndpointConnectionError, BotoCoreError) as error:
            raise StorageUnavailable("Object storage is not reachable") from error

    def get(self, key: str) -> bytes:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            return response["Body"].read()
        except (ClientError, EndpointConnectionError, BotoCoreError) as error:
            raise StorageUnavailable("Object storage is not reachable") from error

    def presigned_get(self, key: str, expires_seconds: int = 900) -> PresignedDownload:
        try:
            url = self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expires_seconds,
            )
        except (ClientError, EndpointConnectionError, BotoCoreError) as error:
            raise StorageUnavailable("Object storage is not reachable") from error
        return PresignedDownload(
            url=url,
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_seconds),
        )


def default_storage() -> ObjectStorage:
    return S3Storage()
