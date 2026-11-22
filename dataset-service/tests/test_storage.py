"""S3 errors are sorted into "file is missing" and "storage is not reachable" (issue #126)."""

import pytest
from botocore.exceptions import ClientError

from app.storage import S3Storage, StorageObjectMissing, StorageUnavailable


def s3_failing_with(code: str) -> S3Storage:
    storage = S3Storage(bucket="datasets", endpoint_url="http://localhost:1", region="us-east-1")

    def get_object(**_kwargs):
        raise ClientError({"Error": {"Code": code, "Message": code}}, "GetObject")

    storage.client.get_object = get_object
    return storage


def test_missing_object_is_reported_as_missing():
    with pytest.raises(StorageObjectMissing):
        s3_failing_with("NoSuchKey").get("dataset-01/v1/data")


def test_other_s3_errors_still_mean_storage_is_unavailable():
    with pytest.raises(StorageUnavailable):
        s3_failing_with("AccessDenied").get("dataset-01/v1/data")
