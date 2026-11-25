"""Create the models, model_versions, releases, deployments and idempotency_keys tables.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = "registry"


def upgrade() -> None:
    # The schema itself already exists (created by the database setup, see migrations/env.py).
    op.create_table(
        "models",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("project_id", sa.String(32), nullable=False),
        sa.Column("mlflow_name", sa.String(200), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "name"),
        schema=SCHEMA,
    )
    op.create_table(
        "model_versions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("model_id", sa.Integer, sa.ForeignKey(f"{SCHEMA}.models.id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("mlflow_run_id", sa.String(64), nullable=False),
        sa.Column("mlflow_version", sa.String(32), nullable=False),
        sa.Column("mlflow_model_id", sa.String(64), nullable=True),
        sa.Column("job_id", sa.String(32), nullable=False),
        sa.Column("dataset_id", sa.String(32), nullable=False),
        sa.Column("dataset_version", sa.Integer, nullable=False),
        sa.Column("metrics", sa.JSON, nullable=False),
        sa.Column("artifact_uri", sa.String(1000), nullable=False),
        sa.Column("registered_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("model_id", "version"),
        sa.UniqueConstraint("model_id", "mlflow_run_id"),
        schema=SCHEMA,
    )
    op.create_table(
        "releases",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("model_id", sa.Integer, sa.ForeignKey(f"{SCHEMA}.models.id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("promoted_by", sa.String(128), nullable=False),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_index("ix_releases_model_id", "releases", ["model_id"], schema=SCHEMA)
    op.create_table(
        "deployments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("model_id", sa.Integer, sa.ForeignKey(f"{SCHEMA}.models.id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("detail", sa.String(500), nullable=False),
        sa.Column("requested_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema=SCHEMA,
    )
    op.create_index("ix_deployments_model_id", "deployments", ["model_id"], schema=SCHEMA)
    op.create_table(
        "idempotency_keys",
        sa.Column("user_id", sa.String(128), primary_key=True),
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("status_code", sa.Integer, nullable=False),
        sa.Column("response_body", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("idempotency_keys", schema=SCHEMA)
    op.drop_index("ix_deployments_model_id", table_name="deployments", schema=SCHEMA)
    op.drop_table("deployments", schema=SCHEMA)
    op.drop_index("ix_releases_model_id", table_name="releases", schema=SCHEMA)
    op.drop_table("releases", schema=SCHEMA)
    op.drop_table("model_versions", schema=SCHEMA)
    op.drop_table("models", schema=SCHEMA)
