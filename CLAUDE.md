# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**MCP Docker CLI Bridge** — a single-file MCP server (`server.py`) that runs inside a Docker container during development and exposes whitelisted CLI commands (pytest, ruff, mypy, etc.) as MCP tools over Streamable HTTP. Claude Code connects to it over a Docker bridge network and calls tools autonomously.

The project ships exactly two files: `server.py` and `requirements.txt`.

## Key Design Decisions (non-negotiable)

- **MCP Streamable HTTP** (not raw HTTP, not SSE). MCP SDK handles routing/framing; `server.py` registers tools and handles calls only.
- **No FastAPI, no shlex, no shell=True.** `subprocess.run(shell=False)` exclusively.
- **Pydantic models** for all internal data: `BridgeConfig`, `CommandEntry`, `CommandsConfig`, `CommandResult`, `LogEntry`. See `doc/SPECS.md §6.1`.
- **Named recipe whitelist** in `commands.json` (mounted read-only). Operator defines commands; caller picks a name.
- **Concurrency via `asyncio.Lock`** — one command at a time. Reject immediately if busy (no queue, no block).
- **Non-zero subprocess exit codes → `isError: false`** (faithful reporting). Only bridge-level failures set `isError: true`.
- **Pre-commit hooks use Node** for JSON parsing (Claude Code container has Node, not Python).

## Development Commands

No running server or test suite yet (implementation phase). Once `server.py` exists:

```bash
# Install dependencies in a venv
pip install -r requirements.txt

# Run the server directly (requires commands.json at BRIDGE_COMMANDS_FILE path)
python server.py

# Lint
ruff check server.py
ruff format server.py

# Type check
mypy server.py
```

### Verifying a Running Server

```bash
# Inspect MCP tools (requires npx / Node)
npx @modelcontextprotocol/inspector http://localhost:7357/mcp

# Or curl a tools/list (Streamable HTTP)
curl -s -X POST http://localhost:7357/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

## Architecture

```
Claude Code ──(MCP/HTTP)──▶ server.py (:7357/mcp) ──(subprocess, shell=False)──▶ pytest, ruff, mypy, etc.
                             inside target container
```

`server.py` has six internal responsibilities (all in one file):

1. **Config loader** — reads `BRIDGE_*` env vars into `BridgeConfig`; parses `commands.json` into `CommandsConfig` (pydantic validates on load, exits non-zero on error)
2. **MCP Tool Provider** — dynamically registers one MCP tool per whitelist entry; tools with `allow_extra_args: true` expose an `args: string[]` schema parameter, others get empty schema
3. **Concurrency guard** — `asyncio.Lock` + module-level variable tracking the in-progress command name; non-blocking acquire, immediate rejection with retry message if busy
4. **Argument validator** — pure function: type-check all args are strings, blocklist scan for `;`, `&&`, `||`, `|`, `` ` ``, `$(`, `>`, `<`
5. **Executor** — whitelist lookup → build argv → `subprocess.run(shell=False, capture_output=True, text=True, timeout=effective_timeout, cwd=entry.cwd)` → `CommandResult`
6. **Request logger** — appends `LogEntry.model_dump_json()` + newline to JSONL file (open/close per write); logs every path including busy rejections

### Request Flow

```
tools/call → acquire lock (reject if busy) → validate args → execute subprocess → log → release lock → return result
```

### Deployment Model

The bridge lives as a **sibling directory** to consumer projects:

```
parent/
├── mcp-docker-cli-bridge/    # this repo
│   ├── server.py
│   └── requirements.txt
├── example-app/              # consumer (example-app project at /mounts/claude-fs/example-app/)
│   ├── commands.json         # whitelist (mounted :ro)
│   ├── .mcp.json             # MCP registration for Claude Code
│   ├── docker-compose.dev.yml
│   └── Dockerfile (dev stage copies bridge/server.py)
```

Consumer provides all integration wiring. Bridge ships only `server.py` + `requirements.txt`.

### Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `BRIDGE_PORT` | `7357` | Listen port |
| `BRIDGE_HOST` | `0.0.0.0` | Bind address |
| `BRIDGE_COMMANDS_FILE` | `/bridge/commands.json` | Whitelist path |
| `BRIDGE_LOG_DIR` | `/bridge/logs` | JSONL log directory |
| `BRIDGE_LOG_FILE` | `bridge.jsonl` | Log file name |

## Implementation Status

See `doc/TODO.md` for the phased plan.

Key spec references:
- `doc/SPECS.md §1` — MCP API contracts (tools/list, tools/call schemas)
- `doc/SPECS.md §2` — commands.json schema
- `doc/SPECS.md §3` — argument validation / metacharacter blocklist
- `doc/SPECS.md §4` — JSONL log format
- `doc/SPECS.md §6.1` — pydantic model definitions
- `doc/SPECS.md §8-9` — consumer integration files (Phase 3)
- `doc/ARCHITECTURE.md` — full system design
- `doc/adr/` — transport and pydantic model rationale
