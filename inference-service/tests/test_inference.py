"""Inference: real predictions from the live version, and the health gate that protects it."""

from pathlib import Path

import pytest

from app import fixture_model
from app.model import PNG_START, Deployment, ModelProblem, fetch_files, load
from tests.conftest import USER, candidate


def predict(client, image: bytes, **form):
    return client.post("/predict", files={"file": ("image.png", image, "image/png")}, data=form, headers=USER)


def test_health_before_any_model(client):
    assert client.get("/health").json() == {"status": "ok", "service": "inference-service"}


def test_predicts_with_the_live_model(client, registry, models, check):
    registry.promote("model-01", 1, models["tiny"])

    response = predict(client, fixture_model.class_image("cat"))

    assert response.status_code == 200, response.text
    body = response.json()
    check(body, "Prediction")
    assert body["model_id"] == "model-01" and body["version"] == 1
    assert body["predictions"][0]["label"] == "cat"  # a real model, really classifying the image
    scores = [p["score"] for p in body["predictions"]]
    assert scores == sorted(scores, reverse=True) and len(scores) == 3


def test_every_class_is_recognised(client, registry, models):
    registry.promote("model-01", 1, models["tiny"])

    found = [
        predict(client, fixture_model.class_image(label)).json()["predictions"][0]["label"]
        for label in ("dog", "ship", "truck")
    ]

    assert found == ["dog", "ship", "truck"]


def test_jpeg_of_any_size_is_resized(client, registry, models):
    import io

    from PIL import Image

    registry.promote("model-01", 1, models["tiny"])
    picture = io.BytesIO()
    Image.new("RGB", (200, 120), (200, 30, 30)).save(picture, format="JPEG")

    assert predict(client, picture.getvalue()).status_code == 200


def test_resnet18_as_the_training_worker_saves_it(client, registry, models, check):
    registry.promote("model-02", 1, models["resnet18"])

    response = predict(client, fixture_model.class_image("cat"), model_id="model-02")

    assert response.status_code == 200, response.text
    check(response.json(), "Prediction")
    assert response.json()["model_id"] == "model-02"


def test_resnet18_in_mlflow_pt2_format(models):
    loaded = load(Deployment("model-02", "resnet", 1, "run-1", models["resnet18_pt2"]), s3_client=None)

    assert len(loaded.predict(fixture_model.class_image("cat"), 3)) == 3


def test_model_info_shows_the_loaded_version(client, registry, models, check):
    assert client.get("/model-info").status_code == 503  # nothing live yet
    registry.promote("model-01", 1, models["tiny"])

    info = client.get("/model-info").json()

    check(info, "ModelInfo")
    assert info["version"] == 1 and info["artifact_uri"] == models["tiny"]


def test_no_live_version_is_503(client, check):
    response = predict(client, fixture_model.class_image("cat"))

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "NO_MODEL_LOADED"
    check(response.json(), "Error")


def test_unknown_model_is_400(client):
    response = predict(client, fixture_model.class_image("cat"), model_id="model-77")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNKNOWN_MODEL"


def test_candidate_is_checked_before_it_goes_live(client, registry, models):
    staged = client.post("/internal/models/model-01/candidates", json=candidate(1, models["tiny"]))
    assert staged.status_code == 200 and staged.json()["status"] == "healthy"
    assert predict(client, fixture_model.class_image("cat")).status_code == 503  # not live until promoted

    registry.promote("model-01", 1, models["tiny"])
    switched = client.post("/internal/models/model-01/refresh")

    assert switched.status_code == 200 and switched.json()["version"] == 1
    assert predict(client, fixture_model.class_image("cat")).json()["version"] == 1


@pytest.mark.parametrize("broken", ["wrong_shape", "missing"])
def test_unhealthy_candidate_is_refused(client, models, broken):
    response = client.post("/internal/models/model-01/candidates", json=candidate(2, models[broken]))

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "MODEL_UNHEALTHY"


def test_failed_new_version_never_replaces_the_healthy_one(client, registry, models):
    registry.promote("model-01", 1, models["tiny"])
    assert predict(client, fixture_model.class_image("cat")).json()["version"] == 1

    registry.promote("model-01", 2, models["wrong_shape"])  # e.g. promoted while this copy was away
    response = predict(client, fixture_model.class_image("cat"))

    assert response.status_code == 200
    assert response.json()["version"] == 1
    assert client.get("/model-info").json()["version"] == 1
    assert client.get("/health").status_code == 200


def test_rollback_switches_back(client, registry, models):
    registry.promote("model-01", 1, models["tiny"])
    predict(client, fixture_model.class_image("cat"))
    registry.promote("model-01", 2, models["resnet18"])
    assert predict(client, fixture_model.class_image("cat")).json()["version"] == 2

    registry.promote("model-01", 1, models["tiny"])

    assert predict(client, fixture_model.class_image("cat")).json()["version"] == 1


def test_keeps_serving_when_the_registry_is_down(client, registry, models):
    registry.promote("model-01", 1, models["tiny"])
    predict(client, fixture_model.class_image("cat"))
    registry.down = True

    assert predict(client, fixture_model.class_image("cat")).status_code == 200


def test_registry_down_and_nothing_loaded_is_503(client, registry):
    registry.down = True

    assert predict(client, fixture_model.class_image("cat")).status_code == 503


def test_not_an_image_is_400(client, registry, models, check):
    registry.promote("model-01", 1, models["tiny"])

    response = client.post("/predict", files={"file": ("notes.txt", b"hello")}, headers=USER)
    broken = predict(client, PNG_START + b"not really a png")

    assert response.status_code == 400
    check(response.json(), "Error")
    assert broken.status_code == 400
    assert broken.json()["error"]["code"] == "INVALID_IMAGE"


def test_empty_model_id_is_422(client):
    # Found by `make contract`: an empty model_id used to be treated as "not sent".
    response = client.post(
        "/predict", files={"file": ("cat.png", PNG_START)}, data={"model_id": ""}, headers=USER
    )

    assert response.status_code == 422


def test_without_login_is_401(client):
    assert client.post("/predict", files={"file": ("cat.png", PNG_START)}).status_code == 401


class FakeS3:
    """Enough of boto3's S3 client for fetch_files."""

    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files

    def get_paginator(self, name):
        files = self.files

        class Pages:
            def paginate(self, Bucket, Prefix):  # noqa: N803 (boto3's argument names)
                yield {"Contents": [{"Key": key} for key in files if key.startswith(Prefix)]}

        return Pages()

    def download_file(self, bucket, key, target):
        Path(target).write_bytes(self.files[key])


def test_model_files_are_read_from_s3(models, tmp_path):
    source = Path(models["tiny"])
    files = {
        f"mlflow/1/models/m-1/artifacts/{path.relative_to(source)}": path.read_bytes()
        for path in source.rglob("*")
        if path.is_file()
    }

    loaded = load(
        Deployment("model-01", "tiny", 1, "run-1", "s3://artifacts/mlflow/1/models/m-1/artifacts"),
        s3_client=lambda: FakeS3(files),
    )

    assert loaded.predict(fixture_model.class_image("cat"), 1)[0]["label"] == "cat"
    with pytest.raises(ModelProblem):
        fetch_files("s3://artifacts/nothing/here", tmp_path, lambda: FakeS3(files))
    with pytest.raises(ModelProblem):
        fetch_files("ftp://elsewhere/model", tmp_path, lambda: FakeS3(files))
