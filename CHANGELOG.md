# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0] - 2026-05-22

Initial release.

### Added

- MCP server over Streamable HTTP (`server.py`, single-file implementation)
- Pydantic-validated `commands.json` whitelist — named command recipes with optional per-command timeouts and `allow_extra_args` control
- `subprocess.run(shell=False)` executor with metacharacter blocklist for argument validation
- `asyncio.Lock`-based concurrency guard — immediate rejection with retry message when busy
- JSONL request logging — every tool call (success, validation rejection, busy rejection) logged with full payload and duration
- Multi-stage `Dockerfile` — base stage for production, dev stage adds pytest/ruff/mypy
- `docker-compose.yml` dev environment with fixed-subnet bridge network
- `commands.dev.json` — self-hosting command whitelist for bridge development
- `hooks/pre-commit` — reference Node.js pre-commit hook implementation
- Full test suite: 43 tests covering all server components

### Architecture

- Transport: MCP Streamable HTTP (not raw HTTP, not SSE)
- No FastAPI, no `shlex`, no `shell=True`
- Request flow: `tools/call` → acquire lock → validate args → execute subprocess → log → release lock → return result
