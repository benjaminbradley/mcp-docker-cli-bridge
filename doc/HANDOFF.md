# Handoff — MCP Docker CLI Bridge

> **Date:** 2026-04-01
> **Status:** Planning complete. Ready for implementation.

---

## What This Project Is

An MCP server that runs inside an application's Docker container during development. It exposes operator-defined CLI commands (tests, linters, type checkers) as MCP tools over Streamable HTTP. Claude Code discovers and calls these tools autonomously over a shared Docker bridge network, closing the loop for AI-assisted development without granting Docker socket access.

## What's Done

All planning documentation is complete and internally consistent:

| Document | Path | Status |
|---|---|---|
| Requirements | `doc/REQUIREMENTS.md` | Approved |
| Architecture | `doc/ARCHITECTURE.md` | Approved |
| Specifications | `doc/SPECS.md` | Approved |
| Implementation Plan | `doc/TODO.md` | Active, Phase 0 next |
| ADR 001 — MCP Transport | `doc/adr/001-mcp-transport.md` | Accepted |
| ADR 002 — Pydantic Models | `doc/adr/002-pydantic-models.md` | Accepted |
| README | `README.md` | Complete with usage docs |

No source code exists yet. The project ships two files: `server.py` and `requirements.txt`.

## Key Design Decisions

- **MCP over Streamable HTTP** (not raw HTTP) — Claude Code gets native tool discovery and typed schemas. See ADR 001.
- **Pydantic for internal models** (not manual dict validation) — already a transitive dep of the MCP SDK. See ADR 002.
- **No FastAPI** — MCP SDK handles routing. **No shlex** — we use `shell=False`, not shell escaping.
- **Named recipe whitelist** in `commands.json` (read-only mount) — operator defines command shape, caller picks a name.
- **Per-command timeout overrides** with global default — in `commands.json`, not env vars.
- **Full payload logging** (stdout/stderr in JSONL) — future: configurable on/off via `BRIDGE_LOG_PAYLOADS`.
- **Pre-commit hook uses Node** for JSON parsing (Claude Code container has Node, not Python).
- **Sibling directory dependency** — bridge project lives alongside consumer projects, not inside them.

## What's Next

**Phase 0 — MCP Server Skeleton, Models, and Config Loader** (see `doc/TODO.md`):

1. `requirements.txt` — `mcp>=1.1.0`
2. `server.py` — pydantic models (`BridgeConfig`, `CommandEntry`, `CommandsConfig`, `CommandResult`, `LogEntry`), config loader, commands loader with pydantic validation, startup banner
3. Tool registration and `tools/list` via MCP SDK

Then Phase 1 (execution), Phase 2 (logging), Phase 3 (integration verification with a consumer project).

## Consumer Project Context

The first consumer will be find-work-bot (`/mounts/claude-fs/find-work-bot/`), which has Phases 0-2 complete (68+ tests, collection pipeline working). The bridge unblocks Claude Code from running tests/lint/typecheck autonomously for Phase 3+ development. Consumer integration files (commands.json, docker-compose.dev.yml, .mcp.json, Dockerfile dev stage) are specced in SPECS.md §8-9 but not yet created.

## Files to Read First in Next Session

1. `doc/HANDOFF.md` — this file (then delete or archive after reading)
2. `doc/TODO.md` — current phase and tasks
3. `doc/SPECS.md` — technical contracts (especially §6.1 for pydantic models, §2 for commands.json schema)
4. `README.md` — usage overview and configuration reference
5. `doc/REQUIREMENTS.md` and `doc/ARCHITECTURE.md` — if broader context needed
