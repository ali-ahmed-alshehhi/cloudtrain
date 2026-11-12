#!/bin/bash
# Print the Python service folders a change touches, one per line. Used by CI to test only those.
#   scripts/changed_services.sh <commit to compare with>
# If a shared file changed (contracts, compose, Makefile, tests, ...) every service is printed,
# because a shared change can break any of them.
set -euo pipefail

all_services=(gateway project-service dataset-service job-service scheduler training model-registry inference-service)
base=${1:-}

# No usable base commit (e.g. the first push of a branch): test everything.
if [ -z "$base" ] || ! git cat-file -e "$base^{commit}" 2>/dev/null; then
  printf '%s\n' "${all_services[@]}"
  exit 0
fi

changed=$(git diff --name-only "$base" HEAD)

if echo "$changed" | grep -qE '^(contracts/|local/|scripts/|tests/|docker-compose\.yml|Makefile|ruff\.toml|requirements-tools\.txt|\.env\.example)'; then
  printf '%s\n' "${all_services[@]}"
  exit 0
fi

for service in "${all_services[@]}"; do
  if echo "$changed" | grep -q "^$service/"; then
    echo "$service"
  fi
done
