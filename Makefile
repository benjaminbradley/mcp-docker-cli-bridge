# Bridge development Makefile — for developing and testing the bridge itself.
# Consumer projects do not use or copy this file. See README.md for integration instructions.

COMPOSE := docker compose -f dev/docker-compose.yml
SANDBOX_NETWORK ?= bridge-dev

# Supply-chain cooldown: pip refuses to install packages uploaded more recently than this.
# Propagated to compose builds, throwaway lock containers, and the Dockerfile ARG default.
# See doc/SECURITY.md for the full list of locations that must stay in sync.
PIP_UPLOADED_PRIOR_TO ?= P3D
export PIP_UPLOADED_PRIOR_TO

.PHONY: help build up down logs test lint typecheck format format-check validate shell install-hooks connect lock lock-upgrade

## help: show this help message
help:
	@grep -E '^## [a-z]' Makefile | sed 's/## /  make /'

## build: build the dev Docker image
build:
	$(COMPOSE) build

## up: start the bridge server in the background
up:
	$(COMPOSE) up -d

## down: stop and remove the bridge container
down:
	$(COMPOSE) down

## logs: tail bridge server logs
logs:
	$(COMPOSE) logs -f my-app

## test: run unit tests inside the container
test:
	$(COMPOSE) run --rm --workdir /workspace --entrypoint "" my-app python -m pytest tests/ -v

## lint: check code style with ruff
lint:
	$(COMPOSE) run --rm --workdir /workspace --entrypoint "" my-app python -m ruff check server.py

## typecheck: run mypy type checker
typecheck:
	$(COMPOSE) run --rm --workdir /workspace --entrypoint "" my-app python -m mypy server.py

## format: auto-format server.py with ruff
format:
	$(COMPOSE) run --rm --workdir /workspace --entrypoint "" my-app python -m ruff format server.py

## format-check: check formatting without modifying files
format-check:
	$(COMPOSE) run --rm --workdir /workspace --entrypoint "" my-app python -m ruff format --check server.py

## validate: run all checks (format-check, lint, typecheck, test)
validate: format-check lint typecheck test

## shell: open a shell in the bridge container
shell:
	$(COMPOSE) run --rm --entrypoint "" my-app sh

## lock: recompile requirements*.txt from requirements*.in (run after editing a .in file)
lock:
	docker run --rm \
	  -e PIP_UPLOADED_PRIOR_TO=$(PIP_UPLOADED_PRIOR_TO) \
	  -v $(CURDIR):/w -w /w python:3.12-slim sh -c "\
	  pip install --no-cache-dir pip-tools >/dev/null && \
	  pip-compile --quiet --strip-extras requirements.in && \
	  pip-compile --quiet --strip-extras requirements-dev.in"

## lock-upgrade: recompile requirements*.txt, upgrading pinned versions to the latest allowed by the .in constraints
lock-upgrade:
	docker run --rm \
	  -e PIP_UPLOADED_PRIOR_TO=$(PIP_UPLOADED_PRIOR_TO) \
	  -v $(CURDIR):/w -w /w python:3.12-slim sh -c "\
	  pip install --no-cache-dir pip-tools >/dev/null && \
	  pip-compile --quiet --strip-extras --upgrade requirements.in && \
	  pip-compile --quiet --strip-extras --upgrade requirements-dev.in"

## install-hooks: install git hooks for bridge development
install-hooks:
	cp dev/hooks/pre-commit .git/hooks/pre-commit
	chmod +x .git/hooks/pre-commit
	@echo "Pre-commit hook installed."

## Connect running devcontainer to sandbox network (run after each rebuild)
connect:
	$(eval DEVCONTAINER := $(shell docker ps \
	  --filter "label=devcontainer.local_folder=$(CURDIR)" \
	  --format "{{.Names}}" | head -1))
	@if [ -z "$(DEVCONTAINER)" ]; then \
	  echo "ERROR: No devcontainer found for $(CURDIR)"; exit 1; \
	fi
	@echo "Connecting $(DEVCONTAINER) to $(SANDBOX_NETWORK)..."
	@docker network connect $(SANDBOX_NETWORK) $(DEVCONTAINER) || true
	@echo "Done"
