# Contributing

## Repo Layout

| Path | Role |
|---|---|
| `server.py`, `requirements.txt` | The published artifact — what consumers receive via the ghcr.io image |
| `requirements.in`, `requirements-dev.in`, `requirements-dev.txt` | Dependency lock inputs / dev lock output — see [Dependencies](#dependencies) |
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

## Dependencies

Python dependencies are locked with [`pip-tools`](https://github.com/jazzband/pip-tools). Loose constraints live in `.in` files; fully-pinned locks (direct + transitive) live in `.txt` files.

| File | Contents | Installed by |
|---|---|---|
| `requirements.in` | Runtime constraints (mcp, pydantic) | — (input only) |
| `requirements.txt` | Locked runtime deps | `Dockerfile` base stage → ghcr.io image |
| `requirements-dev.in` | Dev tool constraints (pytest, ruff, mypy, pip-tools, …) | — (input only) |
| `requirements-dev.txt` | Locked dev deps | `Dockerfile` dev stage |

The dev image includes `pip-tools`, so `pip-compile` is available inside `make shell`. `make lock` itself uses a throwaway `python:3.12-slim` container so it works even when the dev image can't build (e.g., first-time bootstrap, or after breaking edits to `requirements-dev.in`).

### Adding or changing a dependency

1. Edit the appropriate `.in` file (runtime → `requirements.in`, dev-only → `requirements-dev.in`).
2. Recompile the lock files:
   ```bash
   make lock
   ```
3. Rebuild the dev image so the new pins take effect:
   ```bash
   make down && make build && make up && make connect
   ```
4. Commit the `.in` and `.txt` changes together.

### Upgrading pins

`make lock` only recompiles what's needed to satisfy the `.in` constraints — it will not bump an already-pinned version. To pull in newer releases (security fixes, feature updates):

```bash
make lock-upgrade   # bumps all pins to latest allowed by the .in constraints
make down && make build && make up && make connect
make validate       # confirm nothing broke
```

Commit the resulting `.txt` diff on its own so the upgrade is auditable.

### Reviewing a lock diff

When a PR touches `requirements*.txt`:

- Every direct-dep bump should have a corresponding `.in` edit or be attributed to `make lock-upgrade`.
- Transitive-only changes (no `.in` edit, no upgrade run) usually mean an upstream package widened or narrowed its own constraints — inspect the changelog for the direct dep that pulled it in.
- Never edit `requirements*.txt` by hand. Always recompile.

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
