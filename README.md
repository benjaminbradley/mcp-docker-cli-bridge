# Docker CLI Access Bridge

A lightweight MCP (Model Context Protocol) server that grants secure, controlled access to CLI commands inside a Docker container. Designed for AI-assisted development workflows where an external agent (e.g., Claude Code) needs to run tests, linters, and other dev tools inside an application container without Docker socket access.

## Key Properties

- **MCP native** — Exposes whitelisted commands as MCP tools over Streamable HTTP. Claude Code discovers and calls them as first-class tools with typed schemas.
- **Security-first** — Named command recipes with a read-only whitelist config. `subprocess.run` with `shell=False`. No shell injection surface. Schema-enforced constraints prevent unauthorized arguments.
- **Dev-only** — Not part of any production image. Multi-stage Dockerfile integration keeps the bridge out of release builds.
- **Reusable** — Project-agnostic. Configure the command whitelist for any CLI-based project.

## Documentation

- [Requirements](doc/REQUIREMENTS.md) — Functional requirements
- [Architecture](doc/ARCHITECTURE.md) — System design, deployment topology, integration model
- [Specifications](doc/SPECS.md) — MCP API contracts, config schemas, log format, consumer integration specs
- [Implementation Plan](doc/TODO.md) — Phased build plan with verification gates
- `doc/adr/` — Architecture Decision Records

## Quick Start

_See implementation plan (TODO.md) for current status._
