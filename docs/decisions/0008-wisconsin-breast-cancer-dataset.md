# 0008 — Wisconsin Breast Cancer as the tabular use case

- **Status:** accepted
- **Date:** 2026-11-15
- **Decided by:** Abdullah

## Context
CloudTrain needs a second, small use case that exercises CSV preprocessing,
classification metrics, portable model artifacts, and CPU training. It must be
quick enough for local and CI tests and must not require specialized hardware.

## Decision
Use Wisconsin Breast Cancer-style CSV data for `tabular_mlp`. The CSV contains
numeric feature columns and a categorical target column. The target defaults to
`diagnosis`; jobs may override it with the `target_column` extra
hyperparameter.

The trainer makes a seeded stratified train/validation split, learns
standardization statistics from training rows only, and stores feature order,
statistics, target name, class labels, input schema, architecture, and weights
in the final model bundle.

## Consequences
The dataset is small, interpretable, and suitable for fast CPU checks. Uploaded
CSV variants must contain exactly one CSV, finite numeric features, at least two
classes, and at least two rows per class. Reproducibility is expected on the
same software and hardware environment; this decision does not promise
bit-for-bit equality across hardware or PyTorch builds.
