"""Add lineage table (which job used which dataset version).

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

SCHEMA = "datasets"


def upgrade() -> None:
    op.create_table(
        "lineage",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("dataset_id", sa.Integer, sa.ForeignKey(f"{SCHEMA}.datasets.id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("job_id", sa.String(32), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("job_id", "dataset_id", "version", name="uq_lineage_job_dataset_version"),
        schema=SCHEMA,
    )
    op.create_index("ix_lineage_dataset_version", "lineage", ["dataset_id", "version"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_lineage_dataset_version", table_name="lineage", schema=SCHEMA)
    op.drop_table("lineage", schema=SCHEMA)
