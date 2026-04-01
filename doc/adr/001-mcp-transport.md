# ADR 001 — MCP Transport Instead of Raw HTTP

> **Status:** Accepted
> **Date:** 2026-04-01

## Context

The original design used a stdlib-only Python HTTP server (`http.server`) exposing a single `POST /execute` endpoint. The Controller (Claude Code) would call this endpoint via curl or an HTTP client, parse JSON responses, and interpret HTTP status codes to determine success or failure.

This worked, but required the Controller to:
- Know the endpoint URL and request format (documented in CLAUDE.md).
- Construct curl commands or HTTP requests manually.
- Parse raw JSON responses and map HTTP status codes to outcomes.
- Handle connection failures, timeouts, and error payloads with custom logic.

Meanwhile, Claude Code natively supports MCP (Model Context Protocol) servers over Streamable HTTP transport. MCP provides structured tool discovery (`tools/list`), typed input schemas, and standardized error semantics — the exact interface pattern Claude Code already uses for all its tool integrations.

## Decision

Replace the raw `http.server` implementation with a proper MCP server using the Python MCP SDK (`mcp` package). The bridge exposes whitelisted commands as MCP tools over Streamable HTTP transport.

## Consequences

### Positive

- **Native tool integration.** Claude Code discovers available commands via `tools/list` and calls them as first-class tools with typed schemas. No curl, no CLAUDE.md API documentation to maintain.
- **Schema-enforced constraints.** Commands with `allow_extra_args: false` generate tool schemas with no `args` parameter. The constraint is enforced at the protocol level, not just server-side validation.
- **Standard error handling.** MCP defines error semantics that Claude Code already understands: connection errors, tool execution errors, and malformed requests all have protocol-level representations.
- **Ecosystem alignment.** MCP is the standard protocol for AI agent ↔ tool communication. Building on it makes the bridge interoperable with any MCP-compatible client, not just Claude Code.

### Negative

- **Dependency footprint increases.** The server now depends on the `mcp` Python package and its transitive dependencies (`anyio`, `httpx`, `starlette`, `uvicorn`, `pydantic`). The stdlib-only constraint is dropped.
- **Slightly more complex Dockerfile.** The dev stage must install `requirements.txt` in addition to copying `server.py`.

### Neutral

- **Core executor logic unchanged.** The whitelist loader, argument validator, subprocess executor, and JSONL logger are identical. Only the interface layer changes.
- **Operational model unchanged.** The operator still writes a `commands.json`, mounts it read-only, and starts the dev container. The bridge is still removable by deleting the dev overlay files.
- **Pre-commit hook changes slightly.** Curl-based hooks must use JSON-RPC format, or switch to a thin Python MCP client script.

## Alternatives Considered

### Use existing mcp-shell-server (tumf/mcp-shell-server)

Rejected. It uses a flat command allowlist via environment variable, allows the caller to pass arbitrary arguments to any allowed command, has no per-command working directory or extra-args restriction, no JSONL audit logging, and runs over stdio transport only (would need an mcp-proxy sidecar for HTTP). The security model is fundamentally different from our named-recipe whitelist approach.

### Use mcp-shell-server + mcp-proxy sidecar

Rejected. Inherits all the gaps above, plus adds a second process in the container. The two-process architecture is more complex than building a purpose-built MCP server.

### Stay with raw HTTP and wrap in curl

Viable but inferior. The Controller can use curl, but loses tool discovery, typed schemas, and standard error semantics. Every consumer must maintain CLAUDE.md documentation for the API contract. The MCP SDK handles the protocol complexity that we'd otherwise implement manually (or skip).
