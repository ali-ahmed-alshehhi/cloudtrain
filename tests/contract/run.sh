#!/bin/bash
# `make contract`: check every RUNNING service against its file in contracts/openapi/.
#
# Schemathesis reads the contract, sends many generated requests (good and bad ones) and checks
# that each answer is allowed by the contract: right status code, right shape, right content type,
# never a 500. Start everything first with `make up`.
set -u

failed=()

check() {
  local name=$1 address=$2 contract=$3
  echo
  echo "================ $name ($address) against contracts/openapi/$contract"
  if ! schemathesis run "/contracts/openapi/$contract" \
      --url "$address" \
      --max-examples "${CONTRACT_MAX_EXAMPLES:-30}" \
      --header "X-Request-Id: contract-test" \
      --no-color; then
    failed+=("$name")
  fi
}

check gateway           http://gateway:5810           gateway.yaml
check project-service   http://project-service:8001   project-service.yaml
check dataset-service   http://dataset-service:8002   dataset-service.yaml
check job-service       http://job-service:8003       job-service.yaml
check scheduler         http://scheduler:8004         scheduler.yaml
check training-worker   http://training-worker:8010   training-worker.yaml
check model-registry    http://model-registry:8006    model-registry.yaml
check inference-service http://inference-service:8007 inference-service.yaml

echo
if [ ${#failed[@]} -gt 0 ]; then
  echo "CONTRACT CHECK FAILED for: ${failed[*]}"
  exit 1
fi
echo "All services keep their contracts."
