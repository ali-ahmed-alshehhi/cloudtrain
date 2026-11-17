#!/usr/bin/env bash
# Create per-service Postgres roles/schemas on a new RDS instance, and store each
# service DATABASE_URL in Secrets Manager (passwords are never printed).
# Requires: aws CLI, psql, jq, openssl. Run after: terraform apply (enable_database=true)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENVIRONMENT="${ENVIRONMENT:-dev}"
SCHEMAS=(projects datasets jobs scheduler registry mlflow)

# RDS-managed master secret ARN from: terraform output -raw db_master_secret_arn
MASTER_SECRET_ARN="${MASTER_SECRET_ARN:-${SECRET_ID:-}}"
if [[ -z "${MASTER_SECRET_ARN}" ]]; then
  echo "Set MASTER_SECRET_ARN from: terraform output -raw db_master_secret_arn" >&2
  exit 1
fi

echo "Reading master secret (ARN only; password not printed)"
SECRET_JSON=$(aws secretsmanager get-secret-value --secret-id "$MASTER_SECRET_ARN" --query SecretString --output text)
HOST=$(echo "$SECRET_JSON" | jq -r '.host // .HOST')
PORT=$(echo "$SECRET_JSON" | jq -r '.port // .PORT // 5432')
DB=$(echo "$SECRET_JSON" | jq -r '.dbname // .DBNAME // "cloudtrain"')
USER=$(echo "$SECRET_JSON" | jq -r '.username // .USERNAME')
PASS=$(echo "$SECRET_JSON" | jq -r '.password // .PASSWORD')

if [[ -z "$HOST" || "$HOST" == "null" || -z "$PASS" || "$PASS" == "null" ]]; then
  echo "Master secret is missing host/password fields." >&2
  exit 1
fi

export PGPASSWORD="$PASS"
SQL_FILE=$(mktemp)
trap 'rm -f "$SQL_FILE"' EXIT
: >"$SQL_FILE"

put_service_secret() {
  local name="$1"
  local url="$2"
  local secret_name="cloudtrain/${ENVIRONMENT}/database/${name}"

  if aws secretsmanager describe-secret --secret-id "$secret_name" >/dev/null 2>&1; then
    aws secretsmanager put-secret-value --secret-id "$secret_name" --secret-string "$url" >/dev/null
  else
    aws secretsmanager create-secret \
      --name "$secret_name" \
      --description "CloudTrain ${ENVIRONMENT} DATABASE_URL for ${name}" \
      --secret-string "$url" >/dev/null
  fi
  echo "Wrote Secrets Manager secret: ${secret_name}"
}

for name in "${SCHEMAS[@]}"; do
  pw=$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-24)
  printf "CREATE ROLE %s LOGIN PASSWORD '%s';\n" "$name" "$pw" >>"$SQL_FILE"
  printf "CREATE SCHEMA %s AUTHORIZATION %s;\n" "$name" "$name" >>"$SQL_FILE"
  url="postgresql+psycopg://${name}:${pw}@${HOST}:${PORT}/${DB}?sslmode=require"
  put_service_secret "$name" "$url"
done

echo "Applying schemas on ${HOST}:${PORT}/${DB} ..."
psql "host=${HOST} port=${PORT} dbname=${DB} user=${USER} sslmode=require" -v ON_ERROR_STOP=1 -f "$SQL_FILE"
echo "Done. Service DATABASE_URLs are in Secrets Manager under cloudtrain/${ENVIRONMENT}/database/<service>."
echo "SQL template also at: ${ROOT}/scripts/bootstrap-schemas.sql"
