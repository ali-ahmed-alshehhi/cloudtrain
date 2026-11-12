"""Alembic runs this file to apply the migrations in migrations/versions/.

The schema `projects` and its database user are created BEFORE this runs, by the database setup
(locally: the postgres start-up script; in the cloud: the infrastructure setup). The service's own
user is deliberately not allowed to create schemas (least privilege).
"""

import os

from alembic import context
from sqlalchemy import create_engine

from app.db import SCHEMA, Base

engine = create_engine(os.environ["DATABASE_URL"])

with engine.connect() as connection:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        # Keep Alembic's own bookkeeping table in our schema, so services never share it.
        version_table_schema=SCHEMA,
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()
