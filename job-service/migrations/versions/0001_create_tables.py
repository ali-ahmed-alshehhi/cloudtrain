"""Create the jobs, attempts, events, outbox and idempotency_keys tables.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = "jobs"


def upgrade() -> None:
    # The schema itself already exists (created by the database setup, see migrations/env.py).
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("submitted_by", sa.String(128), nullable=False),
        sa.Column("spec", sa.JSON, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempt", sa.Integer, nullable=False),
        sa.Column("machine_type", sa.String(64), nullable=True),
        sa.Column("worker_id", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dlq_requeues", sa.Integer, nullable=False),
        schema=SCHEMA,
    )
    # "The jobs of project X" (GET /jobs) and "every RUNNING job" (the watchdog) are asked all the time.
    op.create_index("ix_jobs_project_id", "jobs", ["project_id"], schema=SCHEMA)
    op.create_index("ix_jobs_status", "jobs", ["status"], schema=SCHEMA)

    op.create_table(
        "attempts",
        sa.Column("job_id", sa.Integer, sa.ForeignKey(f"{SCHEMA}.jobs.id"), primary_key=True),
        sa.Column("number", sa.Integer, primary_key=True),
        sa.Column("machine_type", sa.String(64), nullable=True),
        sa.Column("worker_id", sa.String(128), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(16), nullable=True),
        sa.Column("reason", sa.String(1000), nullable=True),
        schema=SCHEMA,
    )

    op.create_table(
        "events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("job_id", sa.Integer, sa.ForeignKey(f"{SCHEMA}.jobs.id"), nullable=False),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", sa.JSON, nullable=False),
        schema=SCHEMA,
    )
    op.create_index("ix_events_job_id", "events", ["job_id"], schema=SCHEMA)
    op.create_index("ix_events_project_id_id", "events", ["project_id", "id"], schema=SCHEMA)

    op.create_table(
        "outbox",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("queue", sa.String(64), nullable=False),
        sa.Column("body", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tries", sa.Integer, nullable=False),
        sa.Column("last_error", sa.Text, nullable=True),
        schema=SCHEMA,
    )
    op.create_index("ix_outbox_sent_at", "outbox", ["sent_at"], schema=SCHEMA)

    op.create_table(
        "idempotency_keys",
        sa.Column("user_id", sa.String(128), primary_key=True),
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("job_id", sa.Integer, sa.ForeignKey(f"{SCHEMA}.jobs.id"), nullable=False),
        sa.Column("response_body", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("idempotency_keys", schema=SCHEMA)
    op.drop_index("ix_outbox_sent_at", table_name="outbox", schema=SCHEMA)
    op.drop_table("outbox", schema=SCHEMA)
    op.drop_index("ix_events_project_id_id", table_name="events", schema=SCHEMA)
    op.drop_index("ix_events_job_id", table_name="events", schema=SCHEMA)
    op.drop_table("events", schema=SCHEMA)
    op.drop_table("attempts", schema=SCHEMA)
    op.drop_index("ix_jobs_status", table_name="jobs", schema=SCHEMA)
    op.drop_index("ix_jobs_project_id", table_name="jobs", schema=SCHEMA)
    op.drop_table("jobs", schema=SCHEMA)
