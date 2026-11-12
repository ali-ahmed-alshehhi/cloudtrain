"""Create the projects, members and idempotency_keys tables.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = "projects"


def upgrade() -> None:
    # The schema itself already exists (created by the database setup, see migrations/env.py).
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(1000), nullable=True),
        sa.Column("owner_id", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema=SCHEMA,
    )
    op.create_table(
        "members",
        sa.Column("project_id", sa.Integer, sa.ForeignKey(f"{SCHEMA}.projects.id"), primary_key=True),
        sa.Column("user_id", sa.String(128), primary_key=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        schema=SCHEMA,
    )
    # "Which projects is this user in?" is asked on every request, so look it up by user quickly.
    op.create_index("ix_members_user_id", "members", ["user_id"], schema=SCHEMA)
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
    op.drop_index("ix_members_user_id", table_name="members", schema=SCHEMA)
    op.drop_table("members", schema=SCHEMA)
    op.drop_table("projects", schema=SCHEMA)
