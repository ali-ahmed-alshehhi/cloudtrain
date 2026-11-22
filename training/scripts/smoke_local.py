"""Laptop smoke: train one tabular job against injectable LocalStack/MLflow boundaries.

This is the Student 4 acceptance path when AWS is simulated on a laptop:
dataset bytes from a local HTTP download, artifacts in LocalStack S3 (or a
memory fake), and optional live MLflow if MLFLOW_TRACKING_URI is set.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

from app.artifacts import ArtifactStore
from app.models import TrainingJob
from app.trainer import train_cifar

CSV = """radius,texture,perimeter,diagnosis
1.0,1.1,1.2,B
1.1,1.0,1.3,B
0.9,1.2,1.1,B
1.2,1.3,1.4,B
8.0,8.1,8.2,M
8.1,7.9,8.0,M
7.9,8.2,8.1,M
8.2,8.0,8.3,M
"""


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="cloudtrain-smoke-") as folder:
        root = Path(folder)
        (root / "wisconsin.csv").write_text(CSV)
        (root / ".cloudtrain-checksum-sha256").write_text("b" * 64)
        job = TrainingJob.model_validate(
            {
                "job_id": "job-9001",
                "project_id": "project-01",
                "dataset_id": "dataset-01",
                "dataset_version": 1,
                "model": "tabular_mlp",
                "hyperparameters": {
                    "epochs": 1,
                    "batch_size": 4,
                    "learning_rate": 0.05,
                    "seed": 11,
                    "hidden_size": 8,
                },
                "resources": {"gpu_count": 0, "cpu_cores": 2, "memory_gb": 2},
                "parallelism": {"strategy": "single", "world_size": 1},
                "execution": {"max_runtime_minutes": 5, "retry_limit": 0},
            }
        )
        metrics = []

        class MemoryStore:
            def __init__(self) -> None:
                self.final = None

            def load_latest(self, *_):
                return None

            def save_checkpoint(self, *_, **__):
                return "memory://checkpoint"

            def save_final(self, job_id, payload, metadata):
                self.final = (job_id, payload, metadata)
                return f"memory://jobs/{job_id}/model/model-bundle.pt"

        if os.environ.get("S3_ENDPOINT") and os.environ.get("ARTIFACTS_BUCKET"):
            store = ArtifactStore(os.environ["ARTIFACTS_BUCKET"])
        else:
            store = MemoryStore()

        outcome = train_cifar(
            job,
            root,
            lambda epoch, values: metrics.append((epoch, values)),
            threading.Event(),
            artifact_store=store,
        )
        print(
            json.dumps(
                {
                    "metrics": outcome.metrics,
                    "artifact_uri": outcome.artifact_uri,
                    "epochs_logged": len(metrics),
                    "bundle_bytes": len(outcome.model_bundle),
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
