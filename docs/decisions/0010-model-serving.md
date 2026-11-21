# 0010 — How models are saved, served and deployed

- **Status:** proposed (Majed; Abdullah to confirm the model format)
- **Date:** 2026-11-15
- **Decided by:** Majed

## Context
The Model Registry and Inference must serve the models the training worker produces (ResNet-18 on
CIFAR-10 first, a tabular model later) and must never let a broken new version replace a healthy one.
The worker's real model arrives on Fri 20 Nov; serving has to work before then.

## Decision
- **Format:** a model is an MLflow PyTorch model logged in the training run
  (`mlflow.pytorch.log_model(model, name="model", …)`, MLflow's `pickle` format, or `pt2` with a batch
  of one). Image preparation (labels, image size, normalisation) is in the model's MLflow `metadata`,
  defaulting to CIFAR-10. The run carries the tags `project_id`, `job_id`, `dataset_id`, `dataset_version`.
- **Registry:** the MLflow Model Registry holds the versions (and a `production` alias); the schema
  `registry` holds CloudTrain's links, the live version, rollback history and every deployment attempt,
  and is what decides which version is live.
- **Serving:** Inference reads the model files straight from the `artifacts` bucket (the registry
  turns MLflow's `mlflow-artifacts:/` address into the `s3://` place) and runs PyTorch on CPU.
- **Health gate:** before a version goes live, the registry asks Inference to load it and run a
  health check (one prediction on a test image must give one valid score per label). Failed → 503,
  the live version stays, the attempt is recorded. Rollback passes the same gate.
- **Until the real model:** a small CNN trained on synthetic CIFAR-shaped images
  (`inference-service/app/fixture_model.py`) is logged as a normal MLflow run.

## Why
MLflow's PyTorch format is what the worker writes anyway, so there is no export step and any
torchvision model works. Reading from S3 keeps MLflow out of the prediction path, so Inference scales
on its own. Checking a version inside the service that will serve it is the most direct proof that it
can take traffic.

## Trade-offs
- PyTorch makes the inference image large (~1.9 GB, CPU-only build) and slower to start than ONNX
  would; ONNX would need an export step in training.
- `pickle` models run code when loaded: only versions registered from our own MLflow runs, in our own
  bucket, are loaded.
- With several Inference copies (ECS), the registry checks one copy; the others check the version
  themselves when they next ask the registry and keep their old version if it fails.

## Upgrade path
Canary or blue-green (advanced) can build on the same gate: stage the candidate, send it part of the
traffic, then promote.
