"""Helpers for the end-to-end tests. They talk ONLY to the gateway, exactly like the portal does.

Start everything first with `make up`. Settings come from the environment, or from .env:
  GATEWAY_URL     (default http://localhost:5810)
  DEV_AUTH_TOKEN  the laptop dev token, used by `make up` (AUTH_MODE=dev)
  LOGIN=real      log in for real instead: a Cognito ID token for test user Alice, from Salem's
                  security/login on the AWS Emulator (`make e2e-login` sets this up)
"""

import io
import os
import subprocess
import tarfile
import time
from pathlib import Path

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
FIRST_WAIT_SECONDS = 5  # the shared rule: never ask again sooner than 5 seconds...
LONGEST_WAIT_SECONDS = 15  # ...and wait longer each time


def setting(name: str, default: str = "") -> str:
    """Read a setting from the environment, else from the repo's .env file."""
    if os.environ.get(name):
        return os.environ[name]
    env_file = REPO / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            key, _, value = line.partition("=")
            if key.strip() == name:
                return value.strip()
    return default


def real_login() -> bool:
    return setting("LOGIN") == "real"


def login_token() -> str:
    """The token every test sends: a real Cognito ID token for Alice, or the laptop dev token."""
    if not real_login():
        return setting("DEV_AUTH_TOKEN")
    script = REPO / "security" / "login" / "token.sh"
    done = subprocess.run([str(script), "alice"], capture_output=True, text=True, timeout=60)
    if done.returncode != 0:
        pytest.exit(f"Real login failed ({done.stderr.strip()}). Run `make e2e-login`.", returncode=1)
    return done.stdout.strip()


@pytest.fixture(scope="session")
def gateway() -> httpx.Client:
    """An HTTP client logged in through the gateway."""
    url = setting("GATEWAY_URL", "http://localhost:5810")
    token = login_token()
    with httpx.Client(base_url=url, headers={"Authorization": f"Bearer {token}"}, timeout=30) as client:
        try:
            client.get("/health").raise_for_status()
        except httpx.HTTPError:
            pytest.exit(f"The gateway at {url} is not answering. Run `make up` first.", returncode=1)
        yield client


def wait_for(check, what: str, timeout_seconds: float = 120):
    """Call check() until it returns something true. Waits 5 s, then longer each time (back-off)."""
    waited, wait = 0.0, FIRST_WAIT_SECONDS
    while waited < timeout_seconds:
        time.sleep(wait)
        waited += wait
        result = check()
        if result:
            return result
        wait = min(wait * 1.5, LONGEST_WAIT_SECONDS)
    raise AssertionError(f"Gave up after {int(waited)} s waiting for: {what}")


def tiny_image_dataset() -> bytes:
    """A tiny tar.gz shaped like an image dataset (one folder per class), standing in for CIFAR-10."""
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w:gz") as tar:
        for label in ("cat", "dog"):
            content = b"\x89PNG\r\n\x1a\n" + label.encode()
            info = tarfile.TarInfo(f"train/{label}/0.png")
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return archive.getvalue()


def tiny_tabular_dataset() -> bytes:
    """A tiny Wisconsin-style CSV for the laptop/LocalStack walk-through."""
    rows = ["radius,texture,perimeter,diagnosis"]
    for value, label in (
        (1.0, "B"),
        (1.1, "B"),
        (0.9, "B"),
        (1.2, "B"),
        (8.0, "M"),
        (8.1, "M"),
        (7.9, "M"),
        (8.2, "M"),
    ):
        rows.append(f"{value},{value + 0.1},{value + 0.2},{label}")
    return ("\n".join(rows) + "\n").encode()


def small_job(project_id: str, dataset_id: str) -> dict:
    """A job form for the walk-through (CPU only, so it runs on a laptop)."""
    return {
        "project_id": project_id,
        "dataset_id": dataset_id,
        "dataset_version": 1,
        "model": "tabular_mlp",
        "hyperparameters": {
            "epochs": 1,
            "batch_size": 4,
            "learning_rate": 0.05,
            "seed": 7,
            "hidden_size": 8,
        },
        "resources": {"gpu_count": 0, "cpu_cores": 2, "memory_gb": 4},
        "parallelism": {"strategy": "single", "world_size": 1},
        "execution": {"max_runtime_minutes": 10, "retry_limit": 2},
    }


def events_of(gateway: httpx.Client, job_id: str) -> list[dict]:
    response = gateway.get(f"/api/v1/jobs/{job_id}/events")
    response.raise_for_status()
    return response.json()["items"]


def in_inference_container(*command: str) -> bytes:
    """Run Python inside the inference-service container of `make up` (it has PyTorch and MLflow)."""
    done = subprocess.run(
        ["docker", "compose", "exec", "-T", "inference-service", "python", *command],
        cwd=REPO,
        capture_output=True,
        timeout=180,
    )
    assert done.returncode == 0, done.stderr.decode(errors="replace")
    return done.stdout


def links_of(job: dict) -> dict:
    """What a model version is linked to: the job's project, the job, and its dataset version."""
    spec = job["spec"]
    return {
        "project_id": job["project_id"],
        "job_id": job["job_id"],
        "dataset_id": spec["dataset_id"],
        "dataset_version": spec["dataset_version"],
    }


def log_image_test_model(job: dict) -> str:
    """Log the small CIFAR-10-shaped image model (inference-service/app/fixture_model.py) as an
    MLflow run tagged with the job's project, job and dataset, and return its run ID."""
    flags = [f"--{key.replace('_', '-')}={value}" for key, value in links_of(job).items()]
    output = in_inference_container("-m", "app.fixture_model", *flags)
    return output.decode().strip().splitlines()[-1]


def class_image(label: str) -> bytes:
    """A PNG of one CIFAR-10 class, as the image test model learned it."""
    code = f"import sys, app.fixture_model as f; sys.stdout.buffer.write(f.class_image({label!r}))"
    return in_inference_container("-c", code)
