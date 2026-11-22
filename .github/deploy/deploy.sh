#!/usr/bin/env bash
# Deploy one commit's images to an ECS cluster — owner: Salem (Student 9), task #54.
#
#   deploy.sh <cluster> <image-prefix> <tag> <service>...
#   deploy.sh dev-cloudtrain ghcr.io/ali-ahmed-alshehhi/cloudtrain 4999c59 gateway portal ...
#
# For each service: copy the task definition it runs now, change ONLY the image to
# <image-prefix>/<service>:<tag>, register that as a new revision and point the service at it.
# Everything else (CPU, memory, roles, secrets, logs, environment) stays exactly as Terraform set it.
# A rollback is the same command with an older tag: nothing is rebuilt.
#
# With WAIT=1 it waits until ECS reports every service stable. If a new version fails its /health
# check, ECS rolls it back by itself (deployment circuit breaker) and this script fails.
# Writes a table to $GITHUB_STEP_SUMMARY when it is set.
set -euo pipefail

CLUSTER=${1:?cluster}
PREFIX=${2:?image prefix}
TAG=${3:?image tag}
shift 3
[[ $# -gt 0 ]] || { echo "No services given." >&2; exit 2; }

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
summary=${GITHUB_STEP_SUMMARY:-/dev/null}
{
  echo "| Service | Before | Now |"
  echo "|---|---|---|"
} >>"$summary"

for service in "$@"; do
  current=$(aws ecs describe-services --cluster "$CLUSTER" --services "$service" \
    --query 'services[0].taskDefinition' --output text)
  [[ "$current" != "None" && -n "$current" ]] || { echo "Service $service not found in $CLUSTER" >&2; exit 1; }

  aws ecs describe-task-definition --task-definition "$current" --output json >"$work/current.json"

  # Keep only the fields register-task-definition accepts; change only this service's image.
  python3 - "$work/current.json" "$service" "$PREFIX/$service:$TAG" >"$work/new.json" <<'PY'
import json, sys
path, service, image = sys.argv[1:]
task = json.load(open(path))["taskDefinition"]
keep = ["family", "taskRoleArn", "executionRoleArn", "networkMode", "containerDefinitions", "volumes",
        "placementConstraints", "requiresCompatibilities", "cpu", "memory", "pidMode", "ipcMode",
        "proxyConfiguration", "inferenceAccelerators", "ephemeralStorage", "runtimePlatform"]
new = {key: task[key] for key in keep if task.get(key) not in (None, [], {})}
names = [c["name"] for c in new["containerDefinitions"]]
if service not in names:
    sys.exit(f"no container named {service} in {names}")
for container in new["containerDefinitions"]:
    if container["name"] == service:
        container["image"] = image
json.dump(new, sys.stdout)
PY
  before=$(python3 -c "import json,sys; t=json.load(open(sys.argv[1]))['taskDefinition']; print(next(c['image'] for c in t['containerDefinitions'] if c['name']==sys.argv[2]))" "$work/current.json" "$service")

  revision=$(aws ecs register-task-definition --cli-input-json "file://$work/new.json" \
    --query 'taskDefinition.taskDefinitionArn' --output text)
  aws ecs update-service --cluster "$CLUSTER" --service "$service" --task-definition "$revision" >/dev/null

  # Check ECS really runs the new revision now
  running=$(aws ecs describe-services --cluster "$CLUSTER" --services "$service" \
    --query 'services[0].taskDefinition' --output text)
  [[ "$running" == "$revision" ]] || { echo "$service still on $running, expected $revision" >&2; exit 1; }

  echo "deployed $service: ${before##*/} -> $service:$TAG (${revision##*/})"
  echo "| $service | \`${before##*/}\` | \`$service:$TAG\` (${revision##*:}) |" >>"$summary"
done

if [[ "${WAIT:-0}" == "1" ]]; then
  echo "Waiting until every service is stable (a failing version is rolled back by ECS)..."
  aws ecs wait services-stable --cluster "$CLUSTER" --services "$@"
fi
