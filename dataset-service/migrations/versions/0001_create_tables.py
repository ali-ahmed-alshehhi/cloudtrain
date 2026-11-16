"""Create the datasets, versions and idempotency_keys tables.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = "datasets"


def upgrade() -> None:
    op.create_table(
        "datasets",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.String(32), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(1000), nullable=True),
        sa.Column("format", sa.String(16), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema=SCHEMA,
    )
    op.create_index("ix_datasets_project_id", "datasets", ["project_id"], schema=SCHEMA)
    op.create_table(
        "versions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("dataset_id", sa.Integer, sa.ForeignKey(f"{SCHEMA}.datasets.id"), nullable=False),
        sa.Column("number", sa.Integer, nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("storage_uri", sa.String(512), nullable=False),
        sa.Column("object_key", sa.String(512), nullable=False),
        sa.Column("note", sa.String(1000), nullable=True),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("dataset_id", "number", name="uq_versions_dataset_number"),
        schema=SCHEMA,
    )
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
    op.drop_table("versions", schema=SCHEMA)
    op.drop_index("ix_datasets_project_id", table_name="datasets", schema=SCHEMA)
    op.drop_table("datasets", schema=SCHEMA)
