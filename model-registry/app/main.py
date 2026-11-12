"""STAND-IN for the Model Registry (owner: Majed). Replace it with the real service; keep the contract.

What this stand-in already does, as contracts/openapi/model-registry.yaml says: registers versions
(IN MEMORY), promotes one version to production, rolls back to the previous one, and tells Inference
which version is live (GET /models/{id}/production).
What it does NOT do (the real service must): read the run from MLflow (metrics here are empty),
use the MLflow Model Registry and its PostgreSQL schema, check that the new version passes the
inference /health check before it takes traffic, check project membership.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated

from fastapi import Depends, FastAPI, Header, Path, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.common import ApiError, current_user, iso, now_utc, setup_service

SERVICE_NAME = "model-registry"
ModelIdPath = Annotated[str, Path(pattern=r"^model-[0-9]+$")]
VersionPath = Annotated[int, Path(ge=1)]
UserDep = Annotated[str, Depends(current_user)]


class ModelRegister(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(pattern=r"^project-[0-9]+$")
    name: str = Field(min_length=1, max_length=100)
    mlflow_run_id: str = Field(min_length=1, max_length=64)
    job_id: str = Field(pattern=r"^job-[0-9]+$")
    dataset_id: str = Field(pattern=r"^dataset-[0-9]+$")
    dataset_version: int = Field(ge=1)


@dataclass
class Model:
    number: int
    name: str
    project_id: str
    created_at: datetime = field(default_factory=now_utc)
    versions: list[dict] = field(default_factory=list)
    live_history: list[tuple[int, datetime]] = field(
        default_factory=list
    )  # (version, promoted_at), newest last

    @property
    def model_id(self) -> str:
        return f"model-{self.number:02d}"


def model_json(model: Model) -> dict:
    return {
        "model_id": model.model_id,
        "name": model.name,
        "project_id": model.project_id,
        "latest_version": len(model.versions),
        "production_version": model.live_history[-1][0] if model.live_history else None,
        "created_at": iso(model.created_at),
    }


def production_json(model: Model) -> dict:
    version, promoted_at = model.live_history[-1]
    found = model.versions[version - 1]
    return {
        "model_id": model.model_id,
        "name": model.name,
        "version": version,
        "mlflow_run_id": found["mlflow_run_id"],
        "artifact_uri": found["artifact_uri"],
        "promoted_at": iso(promoted_at),
    }


def create_app() -> FastAPI:
    app = FastAPI(title="CloudTrain Model Registry (stand-in)", version="1.0.0")
    setup_service(app, SERVICE_NAME)
    models: dict[int, Model] = {}
    saved_answers: dict[tuple[str, str], dict] = {}

    def find(model_id: str) -> Model:
        model = models.get(int(model_id.removeprefix("model-")))
        if model is None:
            raise ApiError(404, "MODEL_NOT_FOUND", f"Model {model_id} does not exist")
        return model

    def mark_stages(model: Model) -> None:
        live = model.live_history[-1][0] if model.live_history else None
        for version in model.versions:
            if version["version"] == live:
                version["stage"] = "production"
            elif version["stage"] == "production":
                version["stage"] = "archived"

    @app.post("/models", status_code=201)
    def register(
        body: ModelRegister,
        user_id: UserDep,
        idempotency_key: Annotated[
            str | None, Header(alias="Idempotency-Key", min_length=1, max_length=128)
        ] = None,
    ) -> JSONResponse:
        if idempotency_key and (user_id, idempotency_key) in saved_answers:
            return JSONResponse(status_code=201, content=saved_answers[(user_id, idempotency_key)])
        model = next(
            (m for m in models.values() if (m.project_id, m.name) == (body.project_id, body.name)), None
        )
        if model is None:
            model = Model(number=len(models) + 1, name=body.name, project_id=body.project_id)
            models[model.number] = model
        number = len(model.versions) + 1
        version = {
            "model_id": model.model_id,
            "name": model.name,
            "version": number,
            "mlflow_run_id": body.mlflow_run_id,
            "job_id": body.job_id,
            "dataset_id": body.dataset_id,
            "dataset_version": body.dataset_version,
            "metrics": {},  # STAND-IN: the real registry copies the run's metrics from MLflow
            "stage": "none",
            "artifact_uri": f"s3://artifacts/{model.model_id}/v{number}/",
            "created_at": iso(now_utc()),
        }
        model.versions.append(version)
        if idempotency_key:
            saved_answers[(user_id, idempotency_key)] = version
        return JSONResponse(status_code=201, content=version)

    @app.get("/models")
    def list_models(
        user_id: UserDep, project_id: Annotated[str | None, Query(pattern=r"^project-[0-9]+$")] = None
    ) -> dict:
        return {"items": [model_json(m) for m in models.values() if project_id in (None, m.project_id)]}

    @app.get("/models/{model_id}/versions")
    def list_versions(model_id: ModelIdPath, user_id: UserDep) -> dict:
        return {"items": find(model_id).versions}

    @app.get("/models/{model_id}/production")
    def production(model_id: ModelIdPath) -> dict:
        model = find(model_id)
        if not model.live_history:
            raise ApiError(404, "NO_PRODUCTION_VERSION", f"Model {model_id} has no live version yet")
        return production_json(model)

    @app.post("/models/{model_id}/versions/{version}/promote")
    def promote(model_id: ModelIdPath, version: VersionPath, user_id: UserDep) -> dict:
        model = find(model_id)
        if version > len(model.versions):
            raise ApiError(404, "MODEL_VERSION_NOT_FOUND", f"Model {model_id} has no version {version}")
        model.live_history.append((version, now_utc()))
        mark_stages(model)
        return production_json(model)

    @app.post("/models/{model_id}/rollback")
    def rollback(model_id: ModelIdPath, user_id: UserDep) -> dict:
        model = find(model_id)
        if len(model.live_history) < 2:
            raise ApiError(409, "NO_PREVIOUS_VERSION", f"Model {model_id} has no earlier live version")
        model.live_history.pop()
        mark_stages(model)
        return production_json(model)

    return app
