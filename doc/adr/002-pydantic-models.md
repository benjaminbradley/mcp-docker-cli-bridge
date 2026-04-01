# ADR 002 — Pydantic for Internal Data Models

> **Status:** Accepted
> **Date:** 2026-04-01

## Context

The original bridge design used stdlib-only Python with no external dependencies. All data validation was manual: `load_commands()` iterated over parsed JSON dicts checking for required keys and correct types, `log_request()` built dicts by hand, and tool results were manually assembled.

ADR 001 introduced the MCP Python SDK as a dependency, which transitively installs pydantic (for schema validation), starlette (for ASGI), uvicorn (for serving), and related packages. These are now present in the dev container regardless of whether the bridge code uses them directly.

Separately, a review of the Gemini-authored requirements document suggested adopting FastAPI for routing and shlex for shell command safety. These were rejected: the MCP SDK handles its own routing (no need for a separate web framework), and shlex is designed for shell escaping — irrelevant when using `shell=False` subprocess execution, which bypasses the shell entirely.

## Decision

Adopt pydantic for the bridge's internal data models since it is already installed as a transitive dependency of the MCP SDK. Replace manual dict validation with pydantic models for: whitelist configuration, log entries, tool result payloads, and server configuration.

Do not add FastAPI, shlex, or any other new dependencies beyond what the MCP SDK already provides.

## Consequences

### Positive

- **Startup validation becomes declarative.** `load_commands()` reduces to parsing JSON into a pydantic model. Invalid config fails with pydantic's detailed, field-level error messages instead of hand-rolled checks.
- **Log entries are type-safe.** `LogEntry.model_dump_json()` replaces manual dict construction and `json.dumps()`, eliminating a class of serialization bugs.
- **Tool result construction is consistent.** A `CommandResult` model guarantees the stdout/stderr/exit_code structure.
- **Self-documenting.** Model definitions serve as both validation logic and schema documentation.

### Negative

- **Bridge code now imports pydantic directly.** This creates a tighter coupling to the MCP SDK's dependency tree. If a future MCP SDK version dropped pydantic, the bridge would need to add it as an explicit dependency. This is unlikely — pydantic is central to the MCP SDK's design.

### Rejected Additions

- **FastAPI:** The MCP SDK provides its own ASGI application with built-in route handling for the `/mcp` endpoint. A separate web framework would duplicate this and add unnecessary complexity.
- **shlex:** Designed for shell command escaping/quoting. The bridge uses `shell=False`, which passes args directly to `execvp` without shell interpretation. Using shlex would imply shell involvement where there is none, muddying the security model. The metacharacter blocklist remains as defense-in-depth against malformed input.
