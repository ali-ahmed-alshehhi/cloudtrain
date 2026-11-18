#!/usr/bin/env bash
# Start the official AWS Emulator (Student 6 fake AWS account).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

mkdir -p "${HOME}/.aws/emulator"

echo "Building/starting AWS Emulator on https://127.0.0.1:9297 ..."
docker compose -f docker-compose.emulator.yml up -d --build

echo "Waiting for credentials + certificate..."
for _ in $(seq 1 60); do
  if [[ -f "${HOME}/.aws/emulator/9297/emulator_credentials" && -f "${HOME}/.aws/emulator/9297/ca.pem" ]]; then
    echo "AWS Emulator is ready."
    echo "Next:"
    echo "  source ${ROOT}/scripts/emulator-env.sh"
    echo "  terraform init"
    echo "  terraform apply -var-file=environments/dev/emulator.tfvars.example"
    exit 0
  fi
  sleep 1
done

echo "Timed out waiting for emulator files under ~/.aws/emulator/9297/"
echo "Check: docker compose -f docker-compose.emulator.yml logs"
exit 1
