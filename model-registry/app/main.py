"""Model Registry (owner: Majed). Run with:  uvicorn --factory app.main:create_app --port 8006

Contract: contracts/openapi/model-registry.yaml.
- POST /models registers a version from an MLflow run: reads the run and its metrics from MLflow,
  finds the saved model, adds a version to MLflow's Model Registry, and links it to the job and
  dataset version in the PostgreSQL schema `registry`.
- Promote and rollback are health-gated: Inference must load the version and pass its health check
  BEFORE it becomes live. If that fails, the live version does not change (503) and the failed
  attempt is kept in the `deployments` table.
- GET /models/{id}/production tells Inference which version to serve (internal, no login).
- Only members of a model's project may see or change it (asked to the Projects service).
"""

import os
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, Header, Path, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, create_engine, func, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.clients import LINK_TAGS, DeploymentFailed, Inference, Mlflow, Projects, run_metrics, run_tags
from app.common import ApiError, current_user, error_response, iso, setup_service
from app.db import Deployment, Model, ModelVersion, Release, utc_now
from app.idempotency import fingerprint, remember, saved_answer

SERVICE_NAME = "model-registry"
LARGEST_ID = 2**31 - 1  # the biggest number the database's id column can hold

ModelIdPath = Annotated[str, Path(pattern=r"^model-[0-9]+$")]
VersionPath = Annotated[int, Path(ge=1)]
UserDep = Annotated[str, Depends(current_user)]
IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key", min_length=1, max_length=128)]


class ModelRegister(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(pattern=r"^project-[0-9]+$")
    name: str = Field(min_length=1, max_length=100)
    mlflow_run_id: str = Field(min_length=1, max_length=64)
    job_id: str = Field(pattern=r"^job-[0-9]+$")
    dataset_id: str = Field(pattern=r"^dataset-[0-9]+$")
    dataset_version: int = Field(ge=1)


def live_release(model: Model) -> Release | None:
    active = [release for release in model.releases if release.rolled_back_at is None]
    return active[-1] if active else None


def stage_of(model: Model, version: int) -> str:
    live = live_release(model)
    if live and live.version == version:
        return "production"
    if any(release.version == version for release in model.releases):
        return "archived"  # was live once
    return "none"


def version_json(model: Model, found: ModelVersion) -> dict:
    return {
        "model_id": model.public_id,
        "name": model.name,
        "version": found.version,
        "mlflow_run_id": found.mlflow_run_id,
        "job_id": found.job_id,
        "dataset_id": found.dataset_id,
        "dataset_version": found.dataset_version,
        "metrics": found.metrics,
        "stage": stage_of(model, found.version),
        "artifact_uri": found.artifact_uri,
        "created_at": iso(found.created_at),
    }


def model_json(model: Model) -> dict:
    live = live_release(model)
    return {
        "model_id": model.public_id,
        "name": model.name,
        "project_id": model.project_id,
        "latest_version": max((v.version for v in model.versions), default=1),
        "production_version": live.version if live else None,
        "created_at": iso(model.created_at),
    }


def find_version(model: Model, version: int) -> ModelVersion:
    for found in model.versions:
        if found.version == version:
            return found
    raise ApiError(404, "MODEL_VERSION_NOT_FOUND", f"Model {model.public_id} has no version {version}")


def production_json(model: Model) -> dict:
    live = live_release(model)
    if live is None:
        raise ApiError(404, "NO_PRODUCTION_VERSION", f"Model {model.public_id} has no live version yet")
    found = find_version(model, live.version)
    return {
        "model_id": model.public_id,
        "name": model.name,
        "version": live.version,
        "mlflow_run_id": found.mlflow_run_id,
        "artifact_uri": found.artifact_uri,
        "promoted_at": iso(live.promoted_at),
    }


def candidate_json(model: Model, found: ModelVersion) -> dict:
    """What Inference needs to load a version (sent before the version may become live)."""
    return {
        "name": model.name,
        "version": found.version,
        "mlflow_run_id": found.mlflow_run_id,
        "artifact_uri": found.artifact_uri,
    }


def create_app(engine: Engine | None = None, transport: httpx.BaseTransport | None = None) -> FastAPI:
    """`engine` and `transport` let the tests use their own database and fake the other services."""
    engine = engine or create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    sessions = sessionmaker(engine, expire_on_commit=False)
    http = httpx.Client(
        transport=transport, timeout=float(os.environ.get("REGISTRY_CALL_TIMEOUT_SECONDS", "10"))
    )
    bucket = os.environ.get("ARTIFACTS_BUCKET", "artifacts")
    mlflow = Mlflow(
        http,
        os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000"),
        os.environ.get("MLFLOW_ARTIFACTS_DESTINATION") or f"s3://{bucket}/mlflow",
    )
    projects = Projects(http, os.environ.get("PROJECT_SERVICE_URL", "http://project-service:8001"))
    inference = Inference(
        http,
        os.environ.get("INFERENCE_SERVICE_URL", "http://inference-service:8007"),
        float(os.environ.get("DEPLOY_TIMEOUT_SECONDS", "60")),
    )

    def database_ready() -> bool:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except OperationalError:
            return False

    app = FastAPI(title="CloudTrain Model Registry", version="1.0.0")
    logger = setup_service(app, SERVICE_NAME, is_ready=database_ready)

    @app.exception_handler(OperationalError)
    async def database_down(request: Request, error: OperationalError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "unknown")
        return error_response(503, "SERVICE_UNAVAILABLE", "The database is not reachable", request_id)

    def get_session():
        with sessions() as session:
            yield session

    SessionDep = Annotated[Session, Depends(get_session)]

    def load_model(session: Session, model_id: str, lock: bool = False) -> Model:
        number = int(model_id.removeprefix("model-"))
        query = (
            select(Model)
            .where(Model.id == number)
            .options(selectinload(Model.versions), selectinload(Model.releases))
        )
        if lock:  # one promote or rollback of a model at a time
            query = query.with_for_update(of=Model)
        model = session.scalars(query).first() if number <= LARGEST_ID else None
        if model is None:
            raise ApiError(404, "MODEL_NOT_FOUND", f"Model {model_id} does not exist")
        return model

    def record(
        session: Session, model: Model, version: int, action: str, user_id: str, error: str = ""
    ) -> None:
        status = "failed" if error else "succeeded"
        session.add(
            Deployment(
                model_id=model.id,
                version=version,
                action=action,
                status=status,
                detail=error[:500] or "passed the inference health check",
                requested_by=user_id,
            )
        )
        logger.info(f"{action} of {model.public_id} v{version} {status}" + (f": {error}" if error else ""))

    def deploy(session: Session, model: Model, found: ModelVersion, action: str, user_id: str) -> None:
        """The health gate: the version must load and pass Inference's check, or nothing changes."""
        try:
            inference.check_candidate(model.public_id, candidate_json(model, found))
        except DeploymentFailed as failure:
            record(session, model, found.version, action, user_id, error=str(failure))
            session.commit()
            live = live_release(model)
            still = f"version {live.version} stays live" if live else "no version is live"
            raise ApiError(
                503,
                "DEPLOYMENT_FAILED",
                f"Version {found.version} of {model.public_id} failed the inference health check "
                f"({failure}); {still}",
            ) from None

    def went_live(model: Model) -> dict:
        """After the live version changed in our database: tell MLflow and Inference."""
        found = find_version(model, live_release(model).version)
        try:
            mlflow.set_production(model.mlflow_name, found.mlflow_version)
        except ApiError as error:  # our database decides what is live; MLflow's alias only mirrors it
            logger.warning(f"could not move the MLflow alias of {model.public_id}: {error.message}")
        if not inference.switch(model.public_id):
            logger.warning(f"Inference did not switch {model.public_id} now; it will at its next check")
        return production_json(model)

    @app.post("/models", status_code=201)
    def register(
        body: ModelRegister, session: SessionDep, user_id: UserDep, idempotency_key: IdempotencyKey = None
    ) -> JSONResponse:
        request_fingerprint = fingerprint("POST", "/models", body.model_dump())
        if idempotency_key:
            answer = saved_answer(session, user_id, idempotency_key, request_fingerprint)
            if answer:
                return JSONResponse(status_code=201, content=answer)
        projects.require_member(body.project_id, user_id)

        run = mlflow.get_run(body.mlflow_run_id)
        if run["info"].get("status") != "FINISHED":
            raise ApiError(400, "RUN_NOT_FINISHED", f"MLflow run {body.mlflow_run_id} has not finished")
        tags = run_tags(run)
        for name in LINK_TAGS:
            if name in tags and tags[name] != str(getattr(body, name)):
                raise ApiError(
                    400, "RUN_MISMATCH", f"MLflow run {body.mlflow_run_id} belongs to {name} {tags[name]}"
                )
        source, logged_model_id = mlflow.find_model(run)

        model = session.scalars(
            select(Model)
            .where(Model.project_id == body.project_id, Model.name == body.name)
            .with_for_update()
            .options(selectinload(Model.versions), selectinload(Model.releases))
        ).first()
        if model is None:
            model = Model(name=body.name, project_id=body.project_id, mlflow_name="", created_by=user_id)
            session.add(model)
            try:
                session.flush()  # gives the model its number
            except IntegrityError:
                session.rollback()
                raise ApiError(
                    409, "CONFLICT", "The same model was created at the same moment; try again"
                ) from None
            model.mlflow_name = model.public_id
        elif any(v.mlflow_run_id == body.mlflow_run_id for v in model.versions):
            raise ApiError(
                409,
                "RUN_ALREADY_REGISTERED",
                f"Run {body.mlflow_run_id} is already a version of {model.public_id}",
            )
        number = (
            session.scalar(select(func.max(ModelVersion.version)).where(ModelVersion.model_id == model.id))
            or 0
        ) + 1
        links = {"cloudtrain_model_id": model.public_id, "name": body.name, "version": number}
        links |= {name: getattr(body, name) for name in LINK_TAGS}
        mlflow_version = mlflow.register_version(
            model.mlflow_name, source, body.mlflow_run_id, logged_model_id, links
        )
        found = ModelVersion(
            model=model,
            version=number,
            mlflow_run_id=body.mlflow_run_id,
            mlflow_version=mlflow_version,
            mlflow_model_id=logged_model_id,
            job_id=body.job_id,
            dataset_id=body.dataset_id,
            dataset_version=body.dataset_version,
            metrics=run_metrics(run),
            artifact_uri=mlflow.storage_uri(source),
            registered_by=user_id,
            created_at=utc_now(),
        )
        session.add(found)
        session.flush()
        answer = version_json(model, found)
        if idempotency_key:
            remember(session, user_id, idempotency_key, request_fingerprint, answer)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            answer = (
                saved_answer(session, user_id, idempotency_key, request_fingerprint)
                if idempotency_key
                else None
            )
            if answer:
                return JSONResponse(status_code=201, content=answer)
            raise ApiError(
                409, "CONFLICT", "The same model was registered at the same moment; try again"
            ) from None
        logger.info(f"registered {model.public_id} v{number} from MLflow run {body.mlflow_run_id}")
        return JSONResponse(status_code=201, content=answer)

    @app.get("/models")
    def list_models(
        session: SessionDep,
        user_id: UserDep,
        project_id: Annotated[str | None, Query(pattern=r"^project-[0-9]+$")] = None,
    ) -> dict:
        query = (
            select(Model)
            .options(selectinload(Model.versions), selectinload(Model.releases))
            .order_by(Model.id)
        )
        if project_id:
            if projects.status(project_id, user_id) == 403:
                raise ApiError(403, "NOT_A_MEMBER", f"You are not a member of {project_id}")
            query = query.where(Model.project_id == project_id)
        models = list(session.scalars(query))
        member_of = {p: projects.status(p, user_id) == 200 for p in {m.project_id for m in models}}
        return {"items": [model_json(m) for m in models if member_of[m.project_id]]}

    @app.get("/models/{model_id}/versions")
    def list_versions(model_id: ModelIdPath, session: SessionDep, user_id: UserDep) -> dict:
        model = load_model(session, model_id)
        projects.require_member(model.project_id, user_id)
        return {"items": [version_json(model, v) for v in model.versions]}

    @app.get("/models/{model_id}/production")
    def production(model_id: ModelIdPath, session: SessionDep) -> dict:
        return production_json(load_model(session, model_id))

    @app.post("/models/{model_id}/versions/{version}/promote")
    def promote(model_id: ModelIdPath, version: VersionPath, session: SessionDep, user_id: UserDep) -> dict:
        model = load_model(session, model_id, lock=True)
        projects.require_member(model.project_id, user_id)
        found = find_version(model, version)
        live = live_release(model)
        if live and live.version == version:
            return production_json(model)  # already live: nothing to deploy
        deploy(session, model, found, "promote", user_id)
        model.releases.append(
            Release(model_id=model.id, version=version, promoted_by=user_id, promoted_at=utc_now())
        )
        record(session, model, version, "promote", user_id)
        session.commit()
        return went_live(model)

    @app.post("/models/{model_id}/rollback")
    def rollback(model_id: ModelIdPath, session: SessionDep, user_id: UserDep) -> dict:
        model = load_model(session, model_id, lock=True)
        projects.require_member(model.project_id, user_id)
        active = [release for release in model.releases if release.rolled_back_at is None]
        if len(active) < 2:
            raise ApiError(409, "NO_PREVIOUS_VERSION", f"Model {model_id} has no earlier live version")
        current, previous = active[-1], active[-2]
        deploy(session, model, find_version(model, previous.version), "rollback", user_id)
        current.rolled_back_at = utc_now()
        record(session, model, previous.version, "rollback", user_id)
        session.commit()
        return went_live(model)

    return app
