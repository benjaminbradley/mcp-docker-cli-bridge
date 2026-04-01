.PHONY: help build up down logs test lint typecheck format format-check validate shell

## help: show this help message
help:
	@grep -E '^## [a-z]' Makefile | sed 's/## /  make /'

## build: build the dev Docker image
build:
	docker compose build

## up: start the bridge server in the background
up:
	docker compose up -d

## down: stop and remove the bridge container
down:
	docker compose down

## logs: tail bridge server logs
logs:
	docker compose logs -f my-app

## test: run unit tests inside the container
test:
	docker compose run --rm --entrypoint "" my-app python -m pytest tests/ -v

## lint: check code style with ruff
lint:
	docker compose run --rm --entrypoint "" my-app python -m ruff check server.py

## typecheck: run mypy type checker
typecheck:
	docker compose run --rm --entrypoint "" my-app python -m mypy server.py

## format: auto-format server.py with ruff
format:
	docker compose run --rm --entrypoint "" my-app python -m ruff format server.py

## format-check: check formatting without modifying files
format-check:
	docker compose run --rm --entrypoint "" my-app python -m ruff format --check server.py

## validate: run all checks (format-check, lint, typecheck, test)
validate: format-check lint typecheck test

## shell: open a shell in the bridge container
shell:
	docker compose run --rm --entrypoint "" my-app sh
