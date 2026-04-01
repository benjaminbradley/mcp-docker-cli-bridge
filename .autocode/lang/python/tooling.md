# Python Tooling

## Essential Tools

### Package Management: uv (Recommended)
```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create project
uv init myproject
cd myproject

# Add dependencies
uv add requests pydantic
uv add --dev pytest pytest-cov ruff mypy
```

### Alternative: pip + venv
```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

## Linting & Formatting

### Ruff (Recommended - All-in-One)
```toml
# pyproject.toml
[tool.ruff]
line-length = 88
target-version = "py311"

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes
    "I",   # isort
    "B",   # flake8-bugbear
    "UP",  # pyupgrade
]

[tool.ruff.lint.isort]
known-first-party = ["myapp"]
```

```bash
ruff check .          # Lint
ruff check --fix .    # Lint + autofix
ruff format .         # Format
```

### Alternative: Black + isort + flake8
```bash
black .
isort .
flake8 .
```

## Type Checking

### mypy
```toml
# pyproject.toml
[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_ignores = true
```

```bash
mypy src
```

### pyright (Alternative)
```bash
pyright src
```

## Testing

### pytest
```bash
uv add --dev pytest pytest-cov pytest-asyncio
```

```toml
# pyproject.toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "-v --cov=src --cov-report=term-missing"
```

```bash
pytest                    # Run all tests
pytest -x                 # Stop on first failure
pytest -k "test_user"     # Run matching tests
pytest --cov              # With coverage
```

## Project Configuration

### pyproject.toml (Complete Example)
```toml
[project]
name = "myapp"
version = "0.1.0"
description = "My application"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.0",
    "httpx>=0.25",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "pytest-asyncio>=0.21",
    "ruff>=0.1",
    "mypy>=1.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
line-length = 88
target-version = "py311"

[tool.ruff.lint]
select = ["E", "W", "F", "I", "B", "UP"]

[tool.mypy]
python_version = "3.11"
strict = true

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --cov=src"
```

## Development Scripts

### Using uv
```bash
uv run pytest              # Run tests
uv run ruff check .        # Lint
uv run mypy src            # Type check
```

### Using Makefile
```makefile
.PHONY: test lint format typecheck validate

test:
	pytest

lint:
	ruff check .

format:
	ruff format .
	ruff check --fix .

typecheck:
	mypy src

validate: format lint typecheck test
```

## Pre-commit Hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.0.0
    hooks:
      - id: mypy
        additional_dependencies: [pydantic]
```

```bash
pip install pre-commit
pre-commit install
```

## VS Code Settings

```json
// .vscode/settings.json
{
  "python.defaultInterpreterPath": ".venv/bin/python",
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.fixAll.ruff": "explicit",
      "source.organizeImports.ruff": "explicit"
    }
  },
  "python.analysis.typeCheckingMode": "strict"
}
```

## Docker Dev Container

When running tools inside a Docker container instead of a local venv:

- Install with `pip install -e ".[dev]"` (not `pip install -e .`) so that `pytest`, `ruff`, `mypy`, and other dev extras are available inside the container.
- `docker compose run SERVICE COMMAND` passes COMMAND as **arguments** to the image's `ENTRYPOINT`, not as a replacement. To run an arbitrary command, override the entrypoint explicitly:
  ```bash
  docker compose run --rm --entrypoint pytest myservice src/tests/
  docker compose run --rm --entrypoint mypy myservice src/
  # Multi-step: use sh -c
  docker compose run --rm --entrypoint sh myservice -c "ruff format src/ && ruff check --fix src/"
  ```
- After adding a new `docker compose run` tooling target, verify it actually runs the intended tool (check its output, not just the exit code — the default entrypoint may silently succeed with exit 0).

## Project Init Checklist

1. `uv init myproject && cd myproject`
2. `uv add` core dependencies
3. `uv add --dev pytest pytest-cov ruff mypy`
4. Configure pyproject.toml (ruff, mypy, pytest)
5. Create src/ and tests/ directories
6. Add .pre-commit-config.yaml
7. Run `pre-commit install`
8. Add .gitignore (include .venv, __pycache__, .ruff_cache)
