#!/bin/bash
# PostgreSQL start-up script (local only). Runs ONCE, the first time the database volume is empty.
# Creates one database user and one schema per service, each user owning only its own schema.
# The users and passwords are taken from the *_DATABASE_URL settings in .env.
# After changing them, run `make reset` so this script runs again.
set -euo pipefail

create_user_and_schema() {
  local name=$1 url=$2
  # postgresql+psycopg://USER:PASSWORD@postgres:5432/cloudtrain  ->  USER and PASSWORD
  local credentials=${url#*://}
  credentials=${credentials%%@*}
  local user=${credentials%%:*}
  local password=${credentials#*:}
  if [ "$user" != "$name" ]; then
    echo "The user in the $name database URL must be '$name', not '$user'" >&2
    exit 1
  fi
  echo "Creating user and schema: $name"
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
CREATE ROLE $name LOGIN PASSWORD '$password';
CREATE SCHEMA $name AUTHORIZATION $name;
SQL
}

create_user_and_schema projects  "$PROJECTS_DATABASE_URL"
create_user_and_schema datasets  "$DATASETS_DATABASE_URL"
create_user_and_schema jobs      "$JOBS_DATABASE_URL"
create_user_and_schema scheduler "$SCHEDULER_DATABASE_URL"
create_user_and_schema registry  "$REGISTRY_DATABASE_URL"
create_user_and_schema mlflow    "$MLFLOW_DATABASE_URL"
