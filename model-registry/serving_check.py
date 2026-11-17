"""End-to-end check of model serving, through the gateway (Majed's acceptance test).

Needs `make up`. Run from the repo root with the root tools:  .venv/bin/python model-registry/serving_check.py

Until the training worker logs real models (Abdullah), the MLflow runs come from the small test
model in inference-service/app/fixture_model.py, logged from inside the inference container.
Steps: register v1 -> promote -> predict -> register a BROKEN v2 -> its promotion fails and v1
keeps serving -> register v3 -> promote -> rollback to v1.
"""

import io
import os
import subprocess
import sys
import tarfile
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]


def setting(name: str, default: str = "") -> str:
    if os.environ.get(name):
        return os.environ[name]
    for line in (REPO / ".env").read_text().splitlines():
        key, _, value = line.partition("=")
        if key.strip() == name:
            return value.strip()
    return default


def expect(response: httpx.Response, status: int) -> dict:
    if response.status_code != status:
        request = response.request
        sys.exit(f"FAILED: {request.method} {request.url.path} -> {response.status_code} {response.text}")
    return response.json()


def log_test_run(links: dict, broken: bool = False) -> str:
    command = ["docker", "compose", "exec", "-T", "inference-service", "python", "-m", "app.fixture_model"]
    command += [f"--{key.replace('_', '-')}={value}" for key, value in links.items()]
    command += ["--broken"] if broken else []
    output = subprocess.run(command, cwd=REPO, check=True, capture_output=True, text=True).stdout
    return output.strip().splitlines()[-1]


def class_image(label: str) -> bytes:
    command = ["docker", "compose", "exec", "-T", "inference-service", "python", "-c"]
    command += [f"import sys, app.fixture_model as f; sys.stdout.buffer.write(f.class_image('{label}'))"]
    return subprocess.run(command, cwd=REPO, check=True, capture_output=True).stdout


def tiny_dataset() -> bytes:
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w:gz") as tar:
        content = b"\x89PNG\r\n\x1a\ncat"
        info = tarfile.TarInfo("train/cat/0.png")
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))
    return archive.getvalue()


def main() -> None:
    gateway = httpx.Client(
        base_url=setting("GATEWAY_URL", "http://localhost:5810"),
        headers={"Authorization": f"Bearer {setting('DEV_AUTH_TOKEN')}"},
        timeout=30,
    )
    project = expect(gateway.post("/api/v1/projects", json={"name": "Model serving check"}), 201)[
        "project_id"
    ]
    dataset = expect(
        gateway.post(
            "/api/v1/datasets",
            data={"project_id": project, "name": "cifar-10 sample", "format": "tar_gz"},
            files={"file": ("sample.tar.gz", tiny_dataset(), "application/gzip")},
        ),
        201,
    )["dataset_id"]
    job_form = {
        "project_id": project,
        "dataset_id": dataset,
        "dataset_version": 1,
        "model": "resnet18",
        "hyperparameters": {"epochs": 1, "batch_size": 32, "learning_rate": 0.001},
        "resources": {"gpu_count": 0, "cpu_cores": 2, "memory_gb": 4},
        "parallelism": {"strategy": "single", "world_size": 1},
        "execution": {"max_runtime_minutes": 10, "retry_limit": 0},
    }
    job = expect(gateway.post("/api/v1/jobs", json=job_form), 202)["job_id"]
    links = {"project_id": project, "job_id": job, "dataset_id": dataset, "dataset_version": 1}
    name = "cifar10-classifier"
    print(f"project {project}, dataset {dataset}, job {job}")

    def register(run_id: str) -> dict:
        return expect(
            gateway.post("/api/v1/models", json={**links, "name": name, "mlflow_run_id": run_id}), 201
        )

    def predict(label: str) -> dict:
        files = {"file": (f"{label}.png", images[label], "image/png")}
        return expect(gateway.post("/api/v1/predict", files=files, data={"model_id": model_id}), 200)

    images = {label: class_image(label) for label in ("cat", "ship")}

    v1 = register(log_test_run(links))
    model_id = v1["model_id"]
    print(
        f"1. registered {model_id} v{v1['version']}: metrics {v1['metrics']}, files at {v1['artifact_uri']}"
    )
    live = expect(gateway.post(f"/api/v1/models/{model_id}/versions/1/promote"), 200)
    print(f"2. promoted: v{live['version']} is live")
    for label in images:
        answer = predict(label)
        assert answer["version"] == 1 and answer["predictions"][0]["label"] == label, answer
        print(f"3. predicted a {label} image -> {answer['predictions'][0]} (v{answer['version']})")

    v2 = register(log_test_run(links, broken=True))
    failed = gateway.post(f"/api/v1/models/{model_id}/versions/{v2['version']}/promote")
    assert failed.status_code == 503 and failed.json()["error"]["code"] == "DEPLOYMENT_FAILED", failed.text
    print(f"4. broken v{v2['version']} refused: {failed.json()['error']['message']}")
    assert expect(gateway.get(f"/api/v1/models/{model_id}/production"), 200)["version"] == 1
    assert predict("cat")["version"] == 1
    print("5. v1 is still live and still answering")

    v3 = register(log_test_run(links))
    expect(gateway.post(f"/api/v1/models/{model_id}/versions/{v3['version']}/promote"), 200)
    assert predict("cat")["version"] == v3["version"]
    print(f"6. promoted v{v3['version']}; predictions now come from it")
    rolled_back = expect(gateway.post(f"/api/v1/models/{model_id}/rollback"), 200)
    assert rolled_back["version"] == 1 and predict("cat")["version"] == 1
    print("7. rolled back to v1; predictions come from v1 again")
    stages = [
        (v["version"], v["stage"])
        for v in expect(gateway.get(f"/api/v1/models/{model_id}/versions"), 200)["items"]
    ]
    print(f"8. versions and stages: {stages}")
    print("Model serving check passed.")


if __name__ == "__main__":
    main()
