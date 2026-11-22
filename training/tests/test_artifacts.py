"""S3 behavior without a real AWS service."""

import io
import json

from app.artifacts import ArtifactStore, checkpoint_compatible


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.puts: list[str] = []

    def put_object(self, *, Bucket, Key, Body, **_):
        self.puts.append(Key)
        self.objects[(Bucket, Key)] = Body if isinstance(Body, bytes) else Body.read()

    def get_object(self, *, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            error = RuntimeError("NoSuchKey")
            error.response = {"Error": {"Code": "NoSuchKey"}}
            raise error
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}


def test_checkpoint_object_is_written_before_latest_manifest():
    client = FakeS3()
    store = ArtifactStore("artifacts", client=client)
    metadata = {"job_id": "job-1", "schema_version": 1}

    store.save_checkpoint("job-1", 2, b"weights", metadata, is_best=True)

    assert client.puts[0].endswith("/checkpoints/epoch-000002.pt")
    assert client.puts[-1].endswith("/manifests/best.json")
    latest = json.loads(client.objects[("artifacts", "jobs/job-1/manifests/latest.json")])
    assert latest["checkpoint_key"] == client.puts[0]


def test_resume_requires_every_compatibility_field():
    expected = {
        "schema_version": 1,
        "job_id": "job-1",
        "model": "tabular_mlp",
        "dataset_checksum": "abc",
        "hyperparameters": {"epochs": 2},
        "strategy": "single",
        "world_size": 1,
    }
    assert checkpoint_compatible(expected, dict(expected))
    for field in expected:
        incompatible = dict(expected)
        incompatible[field] = "different"
        assert not checkpoint_compatible(incompatible, expected)


def test_incompatible_or_missing_latest_checkpoint_does_not_resume():
    client = FakeS3()
    store = ArtifactStore("artifacts", client=client)
    expected = {
        "schema_version": 1,
        "job_id": "job-1",
        "model": "tabular_mlp",
        "dataset_checksum": "abc",
        "hyperparameters": {},
        "strategy": "single",
        "world_size": 1,
    }

    assert store.load_latest("job-1", expected) is None
    store.save_checkpoint("job-1", 1, b"state", {**expected, "world_size": 2})
    assert store.load_latest("job-1", expected) is None
