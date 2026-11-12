# Schema `mlflow` — MLflow tracking server

**Owner:** Abdullah (Student 4). Created and managed **by MLflow itself** (official image); do not edit
its tables by hand. Other services use the MLflow API, never these tables.
**Holds:** experiments, runs, parameters, metrics, tags, and the model registry (registered models and versions).
Files (models, checkpoints) are in the `artifacts` bucket, not in the database.

## Notes
_MLflow version, how its migrations run on start-up, and how to back it up._
