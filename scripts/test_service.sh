#!/bin/bash
# Run one service's unit tests: scripts/test_service.sh <folder>
# Makes the folder's own .venv the first time (and again whenever its requirements change).
set -euo pipefail

folder=$1
python=${PYTHON:-python3.11}
cd "$folder"

if [ ! -f .venv/.installed ] || [ requirements-dev.txt -nt .venv/.installed ] || [ requirements.txt -nt .venv/.installed ]; then
  echo "Installing libraries for $folder ..."
  "$python" -m venv .venv
  .venv/bin/pip install --quiet --disable-pip-version-check -r requirements-dev.txt
  touch .venv/.installed
fi

.venv/bin/python -m pytest -q -p no:warnings
