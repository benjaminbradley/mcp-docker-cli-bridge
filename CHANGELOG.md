# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

- **Output pipe filtering** — every tool now accepts an optional `pipe` parameter: a Unix-style pipeline string (`2>&1 | grep [-EinABC] 'pat' | head/tail N`) parsed and executed by the bridge (never passed to a shell). Supported operations: stream merge (`2>&1`), `grep` with regex, case-insensitive, line-number, and context flags, `head N`, `tail N`. Unknown flags produce a warning in the response; unknown command names are a hard error.
- **Result caching** — every tool accepts `cache: true` (store full pre-filter output, returns `cache_id`) and `cache_id` (re-apply a `pipe` to a previous result without re-running the command). Cache files are stored at `/tmp/bridge_cache/` with `chmod 0o600`, UUIDs validated before path construction (path traversal prevention), and a 24-hour TTL.
- **Background cache cleanup** — a `_cache_cleanup_loop` task runs every hour via a FastMCP lifespan handler, deleting cache files older than 24 hours without blocking the request path.
- **`CommandResult` extended** — three new optional output fields: `warnings: list[str] | None`, `cache_id: str | None`, `cache_age_ms: int | None`. Fields are omitted from JSON when `None` (`exclude_none=True`), preserving backward compatibility.
- **`tests/server.py` eliminated** — previous workaround for Docker file bind mount inode staleness removed. All tools now run from `cwd: /workspace` using a directory bind mount; `server.py` is always loaded fresh.

### Changed

- `dev/commands.dev.json` — `run_tests`, `run_lint`, `run_typecheck`, `run_format*` all use `cwd: /workspace`; diagnostic `echo_test`/`sleep_test` also updated from `/bridge` to `/workspace`.
- `dev/docker-compose.yml` — removed stale `../tests:/bridge/tests` bind mount; added `..:/workspace` directory mount and `PYTHONPATH=/workspace`; server entrypoint changed to `python /workspace/server.py`.

---

## [0.1.0] - 2026-05-22

Initial release.

### Added

- MCP server over Streamable HTTP (`server.py`, single-file implementation)
- Pydantic-validated `commands.json` allowlist — named command recipes with optional per-command timeouts and `allow_extra_args` control
- `subprocess.run(shell=False)` executor with metacharacter blocklist for argument validation
- `asyncio.Lock`-based concurrency guard — immediate rejection with retry message when busy
- JSONL request logging — every tool call (success, validation rejection, busy rejection) logged with full payload and duration
- Multi-stage `Dockerfile` — base stage for production, dev stage adds pytest/ruff/mypy
- `docker-compose.yml` dev environment with fixed-subnet bridge network
- `commands.dev.json` — self-hosting command allowlist for bridge development
- `hooks/pre-commit` — reference Node.js pre-commit hook implementation
- Full test suite: 43 tests covering all server components

### Architecture

- Transport: MCP Streamable HTTP (not raw HTTP, not SSE)
- No FastAPI, no `shlex`, no `shell=True`
- Request flow: `tools/call` → acquire lock → validate args → execute subprocess → log → release lock → return result
