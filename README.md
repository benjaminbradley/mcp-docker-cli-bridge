# Docker CLI Access Bridge

A lightweight, zero-dependency HTTP bridge that grants secure, controlled access to CLI commands inside a Docker container. Designed for AI-assisted development workflows where an external agent (e.g., Claude Code) needs to run tests, linters, and other dev tools inside an application container without Docker socket access.

## Key Properties

- **Zero dependencies** — stdlib Python only (`http.server`, `subprocess`, `json`). Drops into any Python project without touching its dependency tree.
- **Security-first** — Named command recipes with a read-only whitelist config. `subprocess.run` with `shell=False`. No shell injection surface.
- **Dev-only** — Not part of any production image. Multi-stage Dockerfile integration keeps the bridge out of release builds.
- **Reusable** — Project-agnostic. Configure the command whitelist for any CLI-based project.

## Documentation

- [Requirements](doc/REQUIREMENTS.md) — Functional requirements
- [Architecture](doc/ARCHITECTURE.md) — System design, deployment topology, integration model
- [Specifications](doc/SPECS.md) — API contracts, config schemas, log format, consumer integration specs
- [Implementation Plan](doc/TODO.md) — Phased build plan with verification gates

## Quick Start

_See implementation plan (TODO.md) for current status._
