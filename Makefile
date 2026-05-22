# Bridge development Makefile — for developing and testing the bridge itself.
# Consumer projects do not use or copy this file. See README.md for integration instructions.

COMPOSE := docker compose -f dev/docker-compose.yml

.PHONY: help build up down logs test lint typecheck format format-check validate shell install-hooks

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
	$(COMPOSE) run --rm --entrypoint "" my-app python -m pytest tests/ -v

## lint: check code style with ruff
lint:
	$(COMPOSE) run --rm --entrypoint "" my-app python -m ruff check server.py

## typecheck: run mypy type checker
typecheck:
	$(COMPOSE) run --rm --entrypoint "" my-app python -m mypy server.py

## format: auto-format server.py with ruff
format:
	$(COMPOSE) run --rm --entrypoint "" my-app python -m ruff format server.py

## format-check: check formatting without modifying files
format-check:
	$(COMPOSE) run --rm --entrypoint "" my-app python -m ruff format --check server.py

## validate: run all checks (format-check, lint, typecheck, test)
validate: format-check lint typecheck test

## shell: open a shell in the bridge container
shell:
	$(COMPOSE) run --rm --entrypoint "" my-app sh

## install-hooks: install git hooks for bridge development
install-hooks:
	cp dev/hooks/pre-commit .git/hooks/pre-commit
	chmod +x .git/hooks/pre-commit
	@echo "Pre-commit hook installed."
