# CloudTrain everyday commands. Type `make help` to list them.
# Owner: Ali. Python services use Python 3.11 (change with `make test PYTHON=python3.11`).

PYTHON ?= python3.11
PYTHON_SERVICES := gateway project-service dataset-service job-service scheduler training model-registry inference-service
TOOLS := .venv/bin

.PHONY: help up down reset logs test tools lint contract e2e check

help: ## Show this list
	@grep -E '^[a-z0-9]+:.*## ' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  make %-9s %s\n", $$1, $$2}'

.env: ## (made automatically) your local settings, copied from .env.example
	cp .env.example .env

up: .env ## Start everything and wait until every container is healthy
	docker compose up --detach --build --wait

down: ## Stop everything (data in PostgreSQL is kept)
	docker compose down

reset: ## Stop everything and wipe all data
	docker compose down --volumes --remove-orphans

logs: ## Follow the logs of all containers (Ctrl+C to stop)
	docker compose logs --follow --tail=100

test: ## Unit tests for every Python service
	@for service in $(PYTHON_SERVICES); do \
		echo "== $$service"; \
		PYTHON=$(PYTHON) bash scripts/test_service.sh $$service || exit 1; \
	done
	@echo "== scripts (reviewer rules)"
	@$(MAKE) --silent tools && $(TOOLS)/python -m pytest tests/scripts -q -p no:warnings

# The root tools (ruff, pytest for the integration tests) live in .venv at the repo root.
$(TOOLS)/.installed: requirements-tools.txt
	$(PYTHON) -m venv .venv
	$(TOOLS)/pip install --quiet --disable-pip-version-check -r requirements-tools.txt
	touch $@

tools: $(TOOLS)/.installed ## Install the root tools (ruff, pytest) into .venv

lint: $(TOOLS)/.installed ## Check the style of all Python code with ruff
	$(TOOLS)/ruff check .
	$(TOOLS)/ruff format --check .

contract: .env ## Check every running service against contracts/ (needs `make up`)
	docker compose --profile tools run --rm --build contract-tests

e2e: $(TOOLS)/.installed ## The end-to-end walk-through through the gateway (needs `make up`)
	$(TOOLS)/python -m pytest tests/integration -q -p no:warnings -rs  # -rs: list skipped steps and their owners

check: lint test up contract e2e ## Everything: lint + unit + start + contract + end-to-end
