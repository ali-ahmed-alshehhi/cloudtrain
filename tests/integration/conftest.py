"""Helpers for the end-to-end tests. They talk ONLY to the gateway, exactly like the portal does.

Start everything first with `make up`. Settings come from the environment, or from .env:
  GATEWAY_URL     (default http://localhost:5810)
  DEV_AUTH_TOKEN  the local test token (until Salem's real login is plugged in)
"""

import io
import os
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


@pytest.fixture(scope="session")
def gateway() -> httpx.Client:
    """An HTTP client logged in through the gateway."""
    url = setting("GATEWAY_URL", "http://localhost:5810")
    token = setting("DEV_AUTH_TOKEN")
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
