#!/usr/bin/env bash
# Create per-service Postgres roles/schemas on a new RDS instance.
# Requires: aws CLI, psql, jq. Run after: terraform apply (with enable_database=true)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENVIRONMENT="${ENVIRONMENT:-dev}"
SECRET_ID="cloudtrain/${ENVIRONMENT}/database/master"
SCHEMAS=(projects datasets jobs scheduler registry mlflow)

echo "Reading master secret: ${SECRET_ID}"
SECRET_JSON=$(aws secretsmanager get-secret-value --secret-id "$SECRET_ID" --query SecretString --output text)
HOST=$(echo "$SECRET_JSON" | jq -r .host)
PORT=$(echo "$SECRET_JSON" | jq -r .port)
DB=$(echo "$SECRET_JSON" | jq -r .dbname)
USER=$(echo "$SECRET_JSON" | jq -r .username)
PASS=$(echo "$SECRET_JSON" | jq -r .password)

export PGPASSWORD="$PASS"
SQL_FILE=$(mktemp)
trap 'rm -f "$SQL_FILE"' EXIT

{
  for name in "${SCHEMAS[@]}"; do
    pw=$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-24)
    echo "CREATE ROLE ${name} LOGIN PASSWORD '${pw}';"
    echo "CREATE SCHEMA ${name} AUTHORIZATION ${name};"
    echo "-- ${name} password (store in Secrets Manager / SSM for the service): ${pw}" >&2
  done
} >"$SQL_FILE"

echo "Applying schemas on ${HOST}:${PORT}/${DB} ..."
psql "host=${HOST} port=${PORT} dbname=${DB} user=${USER} sslmode=require" -v ON_ERROR_STOP=1 -f "$SQL_FILE"
echo "Done. Save each service password into Secrets Manager (or your deploy env)."
echo "SQL template also at: ${ROOT}/scripts/bootstrap-schemas.sql"
