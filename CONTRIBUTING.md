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

External contributors: fork the repository on GitHub first, then clone your fork and open pull requests from a topic branch.

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

Python dependencies are locked with [`uv pip compile`](https://docs.astral.sh/uv/). Loose constraints live in `.in` files; fully-pinned locks (direct + transitive) live in `.txt` files. The lock files remain pip-compatible — the Docker images and CI still install with plain `pip`.

| File | Contents | Installed by |
|---|---|---|
| `requirements.in` | Runtime constraints (mcp, pydantic) | — (input only) |
| `requirements.txt` | Locked runtime deps | `Dockerfile` base stage → ghcr.io image |
| `requirements-dev.in` | Dev tool constraints (pytest, ruff, mypy, …) | — (input only) |
| `requirements-dev.txt` | Locked dev deps | `Dockerfile` dev stage |

`make lock` uses a throwaway `python:3.12-slim` container that installs `uv` on the fly and runs `uv pip compile`. This works even when the dev image can't build (e.g., first-time bootstrap, or after breaking edits to `requirements-dev.in`). See `doc/SECURITY.md §6` for the tool choice rationale.

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

### Handling a pip-audit failure

CI's `audit` job fails on any known vulnerability in either lock file. To remediate, bump the affected pin — edit the `.in` constraint if a version bound blocks the fix, then `make lock-upgrade`. Verify locally with `make audit` before pushing.

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

## CI/CD Pipeline

The project uses two GitHub Actions workflows in `.github/workflows/`:

### `ci.yml` — runs on every push to `main` and every PR

- **`docker-validate` job** — Builds the dev Docker image (`docker compose -f dev/docker-compose.yml build`), then runs `ruff format --check`, `ruff check`, `mypy`, and `pytest` inside the container. This is the canonical validation environment because it uses the same tool versions as the published image. Locally reproducible with `make validate`.
- **`audit` job** — Runs [`pip-audit`](https://pypi.org/project/pip-audit/) against `requirements.txt` and `requirements-dev.txt` via the `pypa/gh-action-pip-audit` action, failing on any known CVE in either lock file. Locally reproducible with `make audit`. See [Handling a pip-audit failure](#handling-a-pip-audit-failure).

Both jobs inherit the supply-chain cooldown window (`PIP_UPLOADED_PRIOR_TO: P3D`) at the workflow level — see [`doc/SECURITY.md §6`](doc/SECURITY.md) for the rationale.

### `publish.yml` — runs when a `v*` tag is pushed

Builds the `base` Docker stage and pushes it to `ghcr.io/${{ github.repository }}` with three tags derived from the git tag: `vX.Y.Z`, `vX.Y`, and `latest`. See [Releases](#releases) for how to trigger it. `make build` produces the same image contents locally (without the push).

### Dependabot

`.github/dependabot.yml` schedules monthly PRs that bump pinned GitHub Actions SHAs and refresh the trailing `# vX.Y.Z` comment. Review each Dependabot PR the same way as a human-authored one: read the release notes, skim the SHA-diff link, then merge.

## CI: Third-Party GitHub Actions

**All third-party actions in `.github/workflows/` must be pinned to an immutable commit SHA**, not a mutable tag (`@v1`, `@main`, `@latest`). GitHub Actions resolves the reference fresh at run time, so a compromised maintainer account can retarget a mutable tag to malicious code — this happened publicly in March 2026 with `aquasecurity/trivy-action`, where several `@vX.Y.Z` tags were swapped to secret-exfiltrating code. Pinning to a 40-char SHA makes the reference tamper-evident: the workflow can only ever run the exact commit we vetted.

First-party `actions/*` (checkout, setup-python, etc., all published by GitHub itself) is a slightly lower risk than third-party actions but the same rule applies — pin them too.

### Pin format

```yaml
- uses: pypa/gh-action-pip-audit@f2f5b3d3c8c5e2a1b4d6e8f0a2c4e6g8i0k2m4o6  # v1.0.8
```

The SHA is what actually resolves. The trailing `# vX.Y.Z` comment is for humans reviewing diffs — never rely on it programmatically.

### Looking up a SHA

Two steps: **(1) pick the tag you want**, then **(2) resolve that tag to a SHA**.

**Step 1 — find the appropriate tag.**

For a brand-new pin, the tag is typically the latest stable release (avoid pre-release / RC tags — anything with `-rc`, `-beta`, `-alpha` in the name). Any of these approaches works:

```bash
# gh CLI — lists releases newest-first, skips drafts/prereleases by default
gh release list --repo pypa/gh-action-pip-audit --limit 5

# git plumbing — every tag, sorted (may include prereleases; eyeball the list)
git ls-remote --tags --sort=-v:refname https://github.com/pypa/gh-action-pip-audit | head -10

# Web UI — https://github.com/pypa/gh-action-pip-audit/releases (the "Latest" badge is definitive)
```

For an upgrade, decide the target tag by reading the changelog between the current pin and each candidate. Usually the latest patch on the current major is the low-risk pick; jumping majors requires reading the migration notes.

If the action's docs recommend `@v1` as its stable channel, resolve `v1` as if it were a specific tag — it's a moving pointer to the latest v1.x on the repo, and the resolved SHA at lookup time is what you'll pin (see step 2). The trailing comment should then note the *specific* release the SHA came from (e.g. `# v1.1.0`, not `# v1`) so future reviewers can see version drift.

**Step 2 — resolve the tag to a SHA.**

```bash
# gh CLI (recommended, works for any tag including major-only aliases like v4)
gh api repos/pypa/gh-action-pip-audit/git/ref/tags/v1.1.0 --jq '.object.sha'

# git plumbing, no auth needed
git ls-remote https://github.com/pypa/gh-action-pip-audit refs/tags/v1.1.0
```

Both print the 40-char SHA. Copy it into the workflow with the trailing `# v1.1.0` comment.

**Verify before pinning.** A SHA is only as trustworthy as the moment you looked it up. Before merging a pin (or upgrade), skim the diff between the previous pinned SHA and the new one — GitHub renders this at `https://github.com/OWNER/REPO/compare/OLD_SHA...NEW_SHA`. Look for anything the release notes don't explain.

### Keeping pins fresh

Manual SHA maintenance rots fast. Dependabot understands this pin format and will open PRs that bump the SHA + update the trailing tag comment. The config lives in `.github/dependabot.yml`:

```yaml
version: 2
updates:
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
```

Review each Dependabot PR the same way as a human-authored one: read the release notes, skim the SHA-diff link, then merge.

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
