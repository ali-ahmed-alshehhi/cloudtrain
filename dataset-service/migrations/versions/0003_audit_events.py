"""Add audit_events table (who uploaded, versioned or downloaded which dataset version, and when).

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

SCHEMA = "datasets"


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("dataset_id", sa.Integer, sa.ForeignKey(f"{SCHEMA}.datasets.id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        schema=SCHEMA,
    )
    op.create_index("ix_audit_events_dataset", "audit_events", ["dataset_id", "id"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_audit_events_dataset", table_name="audit_events", schema=SCHEMA)
    op.drop_table("audit_events", schema=SCHEMA)
