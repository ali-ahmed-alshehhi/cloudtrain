"""Laptop smoke: one tabular DDP job with 2 CPU processes (gloo).

For Student 5 (#28): proves Abdullah's runtime already calls ddp.launch /
make_loader / set_epoch / wrap / unwrap. Safe to delete this script later —
it does not change the DDP helpers in training/distributed/.

Usage (from training/):
  python -m scripts.smoke_ddp_local
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
from pathlib import Path

from distributed import ddp

from app.models import TrainingJob
from app.trainer import train_cifar


def _csv() -> str:
    rows = ["radius,texture,perimeter,diagnosis"]
    for index in range(16):
        label = "B" if index < 8 else "M"
        base = 1.0 + index * 0.05 if label == "B" else 8.0 + (index - 8) * 0.05
        rows.append(f"{base},{base + 0.1},{base + 0.2},{label}")
    return "\n".join(rows) + "\n"


class MemoryStore:
    def __init__(self) -> None:
        self.checkpoints = []
        self.final = None

    def load_latest(self, *_):
        return None

    def save_checkpoint(self, job_id, epoch, payload, metadata, *, is_best=False):
        self.checkpoints.append((job_id, epoch, is_best))
        return f"memory://jobs/{job_id}/checkpoints/{epoch}"

    def save_final(self, job_id, payload, metadata):
        self.final = (job_id, len(payload), metadata)
        return f"memory://jobs/{job_id}/model/model-bundle.pt"


def main() -> None:
    if sys.platform == "win32":
        raise SystemExit("DDP process spawn needs macOS/Linux or WSL2")

    with tempfile.TemporaryDirectory(prefix="cloudtrain-ddp-smoke-") as folder:
        root = Path(folder)
        (root / "wisconsin.csv").write_text(_csv())
        (root / ".cloudtrain-checksum-sha256").write_text("c" * 64)
        job = TrainingJob.model_validate(
            {
                "job_id": "job-9002",
                "project_id": "project-01",
                "dataset_id": "dataset-01",
                "dataset_version": 1,
                "model": "tabular_mlp",
                "hyperparameters": {
                    "epochs": 1,
                    "batch_size": 2,
                    "learning_rate": 0.05,
                    "seed": 11,
                    "hidden_size": 8,
                    "num_workers": 0,
                },
                # Contract: for ddp, world_size must equal gpu_count (even on a CPU laptop).
                "resources": {"gpu_count": 2, "cpu_cores": 2, "memory_gb": 2},
                "parallelism": {"strategy": "ddp", "world_size": 2},
                "execution": {"max_runtime_minutes": 5, "retry_limit": 0},
            }
        )
        store = MemoryStore()
        metrics = []
        real_launch = ddp.launch

        def cpu_launch(fn, world_size, args, device="auto"):
            # Force gloo/CPU so this smoke works without a GPU.
            return real_launch(fn, world_size, args=args, device="cpu")

        ddp.launch = cpu_launch
        try:
            outcome = train_cifar(
                job,
                root,
                lambda epoch, values: metrics.append((epoch, values)),
                threading.Event(),
                artifact_store=store,
            )
        finally:
            ddp.launch = real_launch

        print(
            json.dumps(
                {
                    "strategy": "ddp",
                    "world_size": 2,
                    "device": "cpu",
                    "epochs_logged": len(metrics),
                    "checkpoints": len(store.checkpoints),
                    "metrics": outcome.metrics,
                    "artifact_uri": outcome.artifact_uri,
                    "bundle_bytes": len(outcome.model_bundle),
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
