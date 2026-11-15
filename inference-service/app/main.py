"""Inference service (owner: Majed). Run with:  uvicorn --factory app.main:create_app --port 8007

Contract: contracts/openapi/inference-service.yaml.
- POST /predict: a PNG or JPEG image -> the live model version's most likely labels.
- The live version comes from the Model Registry (GET /models/{id}/production); its files are read
  from the artifacts bucket and loaded with MLflow (see app/model.py for the accepted models).
- A version takes traffic only after it passed its health check; a version that fails never
  replaces the one serving (app/store.py).
Internal (never through the gateway, which refuses /internal/ paths):
- POST /internal/models/{model_id}/candidates: load and check a version BEFORE the registry promotes it
- POST /internal/models/{model_id}/refresh: the registry changed the live version; switch now
"""

import logging
import os
from functools import cache
from typing import Annotated

import boto3
import httpx
from botocore.config import Config
from fastapi import Depends, FastAPI, File, Form, Path, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from app.common import ApiError, current_user, iso, setup_service
from app.model import Deployment, InvalidImage, LoadedModel, ModelProblem, load
from app.store import ModelStore, NoModel, Registry, UnknownModel

SERVICE_NAME = "inference-service"
ModelIdPath = Annotated[str, Path(pattern=r"^model-[0-9]+$")]


class Candidate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    version: int = Field(ge=1)
    mlflow_run_id: str
    artifact_uri: str = Field(min_length=1)


@cache
def s3_client():
    """S3 (LocalStack locally: S3_ENDPOINT; in AWS: empty, and the task's IAM role gives access)."""
    endpoint = os.environ.get("S3_ENDPOINT") or None
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
        config=Config(s3={"addressing_style": "path"} if endpoint else {}),
    )


def model_info(loaded: LoadedModel) -> dict:
    deployment = loaded.deployment
    return {
        "model_id": deployment.model_id,
        "name": deployment.name,
        "version": deployment.version,
        "artifact_uri": deployment.artifact_uri,
        "loaded_at": iso(loaded.loaded_at),
    }


def create_app(transport: httpx.BaseTransport | None = None, loader=None) -> FastAPI:
    """`transport` and `loader` let the tests fake the Model Registry and the bucket."""
    default_model = os.environ.get("INFERENCE_DEFAULT_MODEL_ID", "model-01")
    top_k = int(os.environ.get("INFERENCE_TOP_K", "3"))
    max_image_bytes = int(os.environ.get("INFERENCE_MAX_IMAGE_BYTES", str(10 * 1024 * 1024)))
    registry = Registry(
        httpx.Client(transport=transport, timeout=5),
        os.environ.get("MODEL_REGISTRY_URL", "http://model-registry:8006"),
    )

    store = ModelStore(
        registry,
        loader or (lambda deployment: load(deployment, s3_client)),
        float(os.environ.get("INFERENCE_REFRESH_SECONDS", "10")),
        logging.getLogger(SERVICE_NAME),  # set up by setup_service below
    )
    app = FastAPI(title="CloudTrain Inference service", version="1.0.0")
    setup_service(app, SERVICE_NAME, is_ready=lambda: store.healthy(default_model))

    @app.post("/predict")
    async def predict(
        request: Request,
        file: Annotated[UploadFile, File()],
        user_id: Annotated[str, Depends(current_user)],
        model_id: Annotated[str | None, Form(pattern=r"^model-[0-9]+$")] = None,
    ) -> dict:
        # The framework turns an empty form field into "not sent"; the contract says it must match
        # the pattern when it is sent, so look at the raw form too.
        if "model_id" in (await request.form()) and model_id is None:
            raise ApiError(422, "VALIDATION_FAILED", "model_id: must look like model-01")
        image = await file.read(max_image_bytes + 1)
        if len(image) > max_image_bytes:
            raise ApiError(400, "IMAGE_TOO_LARGE", f"Send an image of at most {max_image_bytes} bytes")
        try:
            loaded = await run_in_threadpool(store.current, model_id or default_model)
        except UnknownModel as reason:
            raise ApiError(400, "UNKNOWN_MODEL", str(reason)) from None
        except NoModel as reason:
            raise ApiError(503, "NO_MODEL_LOADED", str(reason)) from None
        try:
            predictions = await run_in_threadpool(loaded.predict, image, top_k)
        except InvalidImage as reason:
            raise ApiError(400, "INVALID_IMAGE", str(reason)) from None
        return {
            "model_id": loaded.deployment.model_id,
            "version": loaded.deployment.version,
            "predictions": predictions,
        }

    @app.get("/model-info")
    def get_model_info() -> dict:
        try:
            return model_info(store.current(default_model))
        except (NoModel, UnknownModel) as reason:
            raise ApiError(503, "NO_MODEL_LOADED", str(reason)) from None

    @app.post("/internal/models/{model_id}/candidates", include_in_schema=False)
    def stage_candidate(model_id: ModelIdPath, body: Candidate) -> dict:
        deployment = Deployment(model_id=model_id, **body.model_dump())
        try:
            loaded = store.stage(deployment)
        except ModelProblem as problem:
            raise ApiError(503, "MODEL_UNHEALTHY", str(problem)) from None
        return {**model_info(loaded), "status": "healthy"}

    @app.post("/internal/models/{model_id}/refresh", include_in_schema=False)
    def refresh(model_id: ModelIdPath) -> dict:
        try:
            return model_info(store.current(model_id, force=True))
        except UnknownModel as reason:
            raise ApiError(404, "UNKNOWN_MODEL", str(reason)) from None
        except NoModel as reason:
            raise ApiError(503, "NO_MODEL_LOADED", str(reason)) from None

    return app
