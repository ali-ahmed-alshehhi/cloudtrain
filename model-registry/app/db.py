"""Database tables of the Model Registry. They all live in the PostgreSQL schema `registry`.

MLflow keeps the runs and its own model registry (schema `mlflow`). These tables keep what is
CloudTrain's: which job and dataset version each model version came from, which version is live,
every deployment attempt (failed ones too) and the history that rollback walks back through.
"""

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, MetaData, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

SCHEMA = "registry"


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA)


class Model(Base):
    __tablename__ = "models"
    __table_args__ = (UniqueConstraint("project_id", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    project_id: Mapped[str] = mapped_column(String(32))
    mlflow_name: Mapped[str] = mapped_column(String(200))  # the registered model's name in MLflow
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    versions: Mapped[list["ModelVersion"]] = relationship(
        back_populates="model", order_by="ModelVersion.version"
    )
    releases: Mapped[list["Release"]] = relationship(order_by="Release.id")

    @property
    def public_id(self) -> str:
        """The ID the outside world sees, e.g. 3 -> "model-03"."""
        return f"model-{self.id:02d}"


class ModelVersion(Base):
    __tablename__ = "model_versions"
    __table_args__ = (UniqueConstraint("model_id", "version"), UniqueConstraint("model_id", "mlflow_run_id"))

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.models.id"))
    version: Mapped[int] = mapped_column(Integer)
    mlflow_run_id: Mapped[str] = mapped_column(String(64))
    mlflow_version: Mapped[str] = mapped_column(String(32))  # MLflow numbers versions on its own
    mlflow_model_id: Mapped[str | None] = mapped_column(String(64))  # MLflow 3 "logged model", if any
    job_id: Mapped[str] = mapped_column(String(32))
    dataset_id: Mapped[str] = mapped_column(String(32))
    dataset_version: Mapped[int] = mapped_column(Integer)
    metrics: Mapped[dict] = mapped_column(JSON)
    artifact_uri: Mapped[str] = mapped_column(String(1000))  # where Inference reads the model files
    registered_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    model: Mapped[Model] = relationship(back_populates="versions")


class Release(Base):
    """One time a version became live. Rollback marks the newest one rolled back."""

    __tablename__ = "releases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.models.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    promoted_by: Mapped[str] = mapped_column(String(128))
    promoted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Deployment(Base):
    """Every promote or rollback attempt and how it ended, failed ones included (the audit trail)."""

    __tablename__ = "deployments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.models.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(16))  # "promote" or "rollback"
    status: Mapped[str] = mapped_column(String(16))  # "succeeded" or "failed"
    detail: Mapped[str] = mapped_column(String(500))
    requested_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class IdempotencyRecord(Base):
    """The first answer to a create request, kept so a repeat with the same key gets the same answer."""

    __tablename__ = "idempotency_keys"

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    status_code: Mapped[int] = mapped_column(Integer)
    response_body: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
