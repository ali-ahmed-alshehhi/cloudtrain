"""S3 checkpoint and final-artifact storage with injectable clients."""

import io
import json
import os
from typing import Any

CHECKPOINT_SCHEMA_VERSION = 1
COMPATIBILITY_FIELDS = (
    "schema_version",
    "job_id",
    "model",
    "dataset_checksum",
    "hyperparameters",
    "strategy",
    "world_size",
)


def checkpoint_compatible(saved: dict[str, Any], expected: dict[str, Any]) -> bool:
    """Resume only when every training-state invariant matches exactly."""
    return all(saved.get(field) == expected.get(field) for field in COMPATIBILITY_FIELDS)


class ArtifactStore:
    def __init__(self, bucket: str, *, client=None) -> None:
        self.bucket = bucket
        self.client = client or self._client_from_environment()

    @staticmethod
    def _client_from_environment():
        import boto3

        options = {"region_name": os.environ.get("AWS_REGION", "us-east-1")}
        endpoint = os.environ.get("S3_ENDPOINT")
        if endpoint:
            options["endpoint_url"] = endpoint
        return boto3.client("s3", **options)

    def save_checkpoint(
        self,
        job_id: str,
        epoch: int,
        payload: bytes,
        metadata: dict[str, Any],
        *,
        is_best: bool = False,
    ) -> str:
        """Publish immutable state first, then pointers, so readers never see partial state."""
        key = f"jobs/{job_id}/checkpoints/epoch-{epoch:06d}.pt"
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=payload,
            ContentType="application/octet-stream",
            Metadata={"checkpoint-schema": str(CHECKPOINT_SCHEMA_VERSION)},
        )
        manifest = json.dumps(
            {"checkpoint_key": key, "epoch": epoch, "metadata": metadata},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        self._put_manifest(job_id, "latest", manifest)
        if is_best:
            self._put_manifest(job_id, "best", manifest)
        return key

    def load_latest(self, job_id: str, expected: dict[str, Any]) -> bytes | None:
        try:
            manifest = json.loads(self._get(f"jobs/{job_id}/manifests/latest.json"))
        except Exception as error:
            if _is_missing(error):
                return None
            raise
        if not checkpoint_compatible(manifest.get("metadata", {}), expected):
            return None
        return self._get(manifest["checkpoint_key"])

    def save_final(self, job_id: str, payload: bytes, metadata: dict[str, Any]) -> str:
        key = f"jobs/{job_id}/model/model-bundle.pt"
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=payload,
            ContentType="application/octet-stream",
        )
        self._put_manifest(
            job_id,
            "final",
            json.dumps({"artifact_key": key, "metadata": metadata}, sort_keys=True).encode(),
        )
        return key

    def _put_manifest(self, job_id: str, name: str, body: bytes) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=f"jobs/{job_id}/manifests/{name}.json",
            Body=body,
            ContentType="application/json",
        )

    def _get(self, key: str) -> bytes:
        body = self.client.get_object(Bucket=self.bucket, Key=key)["Body"]
        return body.read() if hasattr(body, "read") else io.BytesIO(body).read()


def _is_missing(error: Exception) -> bool:
    response = getattr(error, "response", {})
    code = response.get("Error", {}).get("Code")
    return code in {"NoSuchKey", "404", "NotFound"}


def store_from_environment() -> ArtifactStore:
    return ArtifactStore(os.environ["ARTIFACTS_BUCKET"])
