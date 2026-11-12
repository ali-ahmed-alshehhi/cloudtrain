#!/bin/bash
# Create the team's GitHub labels, milestones, project board and issues (scripts/create_tasks.py).
#   bash scripts/create_tasks.sh            # DRY RUN: only shows what would be created
#   bash scripts/create_tasks.sh --apply    # really create them (safe to run again)
set -euo pipefail
cd "$(dirname "$0")/.."
make --silent tools
exec .venv/bin/python scripts/create_tasks.py "$@"
