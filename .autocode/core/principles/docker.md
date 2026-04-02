# Docker Principles

## Non-Root User (mandatory)

Least privilege principle dictates that application containers must always run as a non-root user.

**Pattern for Debian-based images (`python:*-slim`, `node:*-slim`, etc.):**

```dockerfile
# Create user AFTER pip/npm installs (which run as root) but BEFORE USER switch.
# UID 1000 matches the default first user on most Linux hosts, ensuring
# volume-mounted directories are writable without extra host configuration.
RUN useradd --uid 1000 --no-create-home appuser \
    && chown -R appuser:appuser /app
USER appuser

ENTRYPOINT [...]
```

The `USER` directive must appear **after** all `COPY`, `RUN pip install`, and `RUN chown` steps — anything that needs root goes before it.

## Volume Ownership

When a container mounts host directories for write access, the container UID must match the host file owner UID, or writes will fail with `Permission denied`.

- **Strategy:** Use `--uid 1000` to match the default Linux developer UID.
- **Read-only mounts** (`:ro`) are not affected — ownership doesn't matter.
- **Secret files** (Docker secrets at `/run/secrets/`) are mounted read-only by Docker automatically.

If UID alignment is not possible, set the service user in `docker-compose.yml`:

```yaml
services:
  myservice:
    user: "${UID:-1000}:${GID:-1000}"
```

## Least-Privilege Mounts

Only mount directories the container actually needs to write. Mark everything else read-only:

```yaml
volumes:
  - ./src:/app/src          # writable: editable install, live reload
  - ./data:/app/data        # writable: runtime output
  - ./config:/app/config:ro # read-only: config files never written at runtime
```

## Dev Container Signal

If a test must work around a permission check (e.g., using a file path where a directory is expected to trigger `NotADirectoryError` instead of `PermissionError`), treat this as a signal that the container is running as root — and fix the container, not the test.

`chmod`-based permission tests are correct and idiomatic when the container runs as a non-root user. They are the expected pattern.

## Source File Bind Mounts — Use Directory Mounts, Not File Mounts

**File bind mounts go stale when the host editor atomically replaces a file.**

Many editors and tools (including Claude Code's Edit tool) write changes atomically: write to a temp file, then rename it over the original. This creates a **new inode**. Docker file bind mounts are inode-based — the container continues to see the original inode and never receives the new content.

**Symptom:** Linters (ruff, mypy) pass because they read from the filesystem path directly. But Python's import system loads from a stale `.pyc` or the stale inode file — `pytest` fails with `ImportError` or `IndentationError` on code that was just edited.

**Rule:** Never use file bind mounts for source files that will be edited during development:

```yaml
# BAD — file bind mount goes stale after atomic edits
volumes:
  - ./server.py:/app/server.py

# GOOD — directory bind mount always reflects current content
volumes:
  - .:/workspace
environment:
  - PYTHONPATH=/workspace
```

For Python projects, set `PYTHONPATH` to the directory-mounted workspace path so `pytest` finds the fresh source before any in-container copy.

If a file bind mount is unavoidable (e.g. read-only config), this is less of a concern since the file is not being edited during the container's lifetime.

## Dockerfile Layer Order

Maximize cache reuse and minimize rebuild time:

1. `COPY` dependency manifests (`requirements.txt`, `package.json`)
2. `RUN` dependency install (cache-busted only when manifests change)
3. `COPY` application source
4. `RUN` application install / build
5. `RUN` create non-root user + `chown`
6. `USER` switch
7. `ENTRYPOINT` / `CMD`
