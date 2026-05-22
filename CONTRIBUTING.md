# Contributing

## Repo Layout

| Path | Role |
|---|---|
| `server.py`, `requirements.txt` | The published artifact — what consumers receive via the ghcr.io image |
| `Dockerfile` | Builds the ghcr.io image (`base` stage) and the dev image (`dev` stage) |
| `dev/docker-compose.yml`, `dev/commands.dev.json` | Bridge self-hosting scaffolding — used when developing the bridge itself |
| `Makefile`, `dev/hooks/pre-commit` | Bridge contributor tooling — not needed by consumers |

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- `make`

## Getting Started

```bash
git clone https://github.com/your-username/mcp-docker-cli-bridge.git
cd mcp-docker-cli-bridge

# Build the dev image
make build

# Start the bridge server (self-hosting mode)
make up

# Run the full validation suite
make validate
```

## Self-Hosting Development

This project uses itself during development — the bridge server runs inside the `my-app` container and exposes tools (`run_tests`, `run_lint`, `run_typecheck`, `run_format_check`) that Claude Code calls to work on the codebase.

The dev environment is defined in `dev/docker-compose.yml` and `dev/commands.dev.json`.

## Development Commands

```bash
make test          # Run unit tests
make lint          # ruff check
make typecheck     # mypy
make format        # ruff format (modifies files)
make format-check  # ruff format --check (no changes)
make validate      # format-check + lint + typecheck + test
make shell         # Open a shell in the container
make logs          # Tail bridge server logs
```

All commands run inside the Docker container. No local Python environment needed.

## Pre-Commit Hook

The `dev/hooks/pre-commit` script runs all checks via the bridge before each commit. It requires the bridge server to be running (`make up`).

```bash
make install-hooks
```

This copies `dev/hooks/pre-commit` to `.git/hooks/pre-commit`. Remove it with `rm .git/hooks/pre-commit`.

The hook is written in Node.js because the bridge dev environment uses a Node-based devcontainer. If your setup doesn't have Node, the same checks are available via `make validate`. Alternatively, reimplement the hook in any language — the underlying MCP-over-HTTP protocol is language-agnostic (see the comment at the top of `dev/hooks/pre-commit`).

## Pull Requests

- Follow [conventional commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `test:`, `refactor:`
- All tests must pass (`make validate`)
- One logical change per PR
- Update `CHANGELOG.md` for user-visible changes

## Releases

Releases are tag-driven. Pushing a `v*` tag triggers `.github/workflows/publish.yml`, which builds the `base` Docker stage and pushes it to `ghcr.io/owner/mcp-docker-cli-bridge` with `vX.Y.Z`, `vX.Y`, and `latest` tags.

```bash
git tag v0.2.0
git push --tags
```

The CI workflow (`.github/workflows/ci.yml`) runs on every push to `main` and on all PRs — both a fast host-Python job and a Docker-in-container job that mirrors the published image.
