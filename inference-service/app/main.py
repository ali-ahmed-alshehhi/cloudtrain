"""STAND-IN for the Inference service (owner: Majed). Replace it with the real service; keep the contract.

What this stand-in already does: accepts an image (PNG or JPEG) and answers a FIXED prediction in the
shape of contracts/openapi/inference-service.yaml; GET /model-info answers a fixed model.
What it does NOT do (the real service must): ask the Model Registry which version is live, load that
model from S3, and run it on the image.
"""

from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile

from app.common import ApiError, current_user, iso, now_utc, setup_service

SERVICE_NAME = "inference-service"
PNG_START = b"\x89PNG\r\n\x1a\n"
JPEG_START = b"\xff\xd8\xff"
FIXED_MODEL = {
    "model_id": "model-01",
    "name": "resnet18-cifar10",
    "version": 1,
    "artifact_uri": "s3://artifacts/model-01/v1/",
}


def create_app() -> FastAPI:
    app = FastAPI(title="CloudTrain Inference service (stand-in)", version="1.0.0")
    setup_service(app, SERVICE_NAME)
    loaded_at = iso(now_utc())

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
        image = await file.read()
        if not image.startswith((PNG_START, JPEG_START)):
            raise ApiError(400, "INVALID_IMAGE", "Send a PNG or JPEG image")
        return {
            "model_id": model_id or FIXED_MODEL["model_id"],
            "version": FIXED_MODEL["version"],
            "predictions": [  # STAND-IN: always the same answer
                {"label": "cat", "score": 0.62},
                {"label": "dog", "score": 0.21},
                {"label": "truck", "score": 0.17},
            ],
        }

    @app.get("/model-info")
    def model_info() -> dict:
        return {**FIXED_MODEL, "loaded_at": loaded_at}

    return app
