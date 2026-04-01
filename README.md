# MCP Docker CLI Bridge

An MCP (Model Context Protocol) server that gives AI development agents secure, controlled access to CLI commands inside a Docker container. Built for workflows where Claude Code needs to run tests, linters, and dev tools inside an application container without Docker socket access.

## How It Works

The bridge runs inside your application's Docker container during development. It reads a `commands.json` whitelist that you define, and exposes each command as an MCP tool over Streamable HTTP. Claude Code discovers the tools automatically and calls them like any other MCP tool.

```
Claude Code ──(MCP over HTTP)──▶ Bridge Server ──(subprocess)──▶ pytest, ruff, mypy, etc.
                                  inside your app container
```

## Key Properties

- **MCP native** — Whitelisted commands appear as MCP tools with typed schemas. Claude Code discovers and calls them automatically.
- **Security-first** — Named command recipes with a read-only whitelist config. `subprocess.run` with `shell=False`. Schema-enforced constraints prevent unauthorized arguments.
- **Dev-only** — Multi-stage Dockerfile integration keeps the bridge out of production images.
- **Reusable** — Project-agnostic. Configure the command whitelist for any CLI-based project.

## Quick Start

### 1. Create the bridge network

```bash
docker network create dev-bridge
```

### 2. Define your command whitelist

Create `commands.json` in your project root:

```json
{
  "default_timeout": 60,
  "commands": {
    "run_tests": {
      "command": ["python", "-m", "pytest", "src/tests/", "-v"],
      "allow_extra_args": true,
      "cwd": "/app",
      "timeout": 120
    },
    "run_lint": {
      "command": ["python", "-m", "ruff", "check", "src/"],
      "allow_extra_args": false,
      "cwd": "/app"
    },
    "run_typecheck": {
      "command": ["python", "-m", "mypy", "src/"],
      "allow_extra_args": false,
      "cwd": "/app"
    }
  }
}
```

Each command defines:
- `command` — the executable and its fixed arguments (passed as a list, never through a shell)
- `allow_extra_args` — whether the caller can append arguments (e.g., `--tb=short` for pytest). When `false`, the tool schema doesn't expose an args parameter at all.
- `cwd` — working directory inside the container
- `timeout` — (optional) per-command timeout in seconds; falls back to `default_timeout`

### 3. Add the bridge to your Dockerfile

Add a `dev` stage that extends your production image:

```dockerfile
FROM base AS dev
RUN pip install -e ".[dev]"
COPY bridge/server.py /bridge/server.py
COPY bridge/requirements.txt /bridge/requirements.txt
RUN pip install --no-cache-dir -r /bridge/requirements.txt
CMD ["python", "/bridge/server.py"]
```

### 4. Create a dev compose override

`docker-compose.dev.yml`:

```yaml
services:
  app:
    build:
      target: dev
      additional_contexts:
        bridge: ../mcp-docker-cli-bridge
    volumes:
      - ./src:/app/src
      - ./commands.json:/bridge/commands.json:ro
      - ./data/bridge-logs:/bridge/logs
    networks:
      - default
      - dev-bridge
    expose:
      - "7357"

networks:
  dev-bridge:
    external: true
    name: ${BRIDGE_NETWORK:-dev-bridge}
```

### 5. Start the dev environment

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

The bridge server starts and logs the loaded commands:

```
Bridge listening on 0.0.0.0:7357
Loaded 3 commands: run_tests (timeout: 120s), run_lint (timeout: 60s), run_typecheck (timeout: 60s)
```

### 6. Register with Claude Code

Add `.mcp.json` to your project root:

```json
{
  "mcpServers": {
    "dev-bridge": {
      "type": "http",
      "url": "http://app:7357/mcp"
    }
  }
}
```

Or register via CLI:
```bash
claude mcp add --transport http dev-bridge http://app:7357/mcp --scope local
```

Claude Code now discovers `run_tests`, `run_lint`, and `run_typecheck` as tools and can call them autonomously.

## Configuration Reference

### Environment Variables (server settings)

| Variable | Default | Description |
|---|---|---|
| `BRIDGE_PORT` | `7357` | Port the MCP server listens on |
| `BRIDGE_HOST` | `0.0.0.0` | Bind address |
| `BRIDGE_COMMANDS_FILE` | `/bridge/commands.json` | Path to the whitelist config |
| `BRIDGE_LOG_DIR` | `/bridge/logs` | Directory for the JSONL audit log |
| `BRIDGE_LOG_FILE` | `bridge.jsonl` | Log file name |

### commands.json (command whitelist)

| Field | Type | Required | Description |
|---|---|---|---|
| `default_timeout` | int | No | Global timeout in seconds (default: 60) |
| `commands` | object | Yes | Map of command name → definition |
| `commands.*.command` | string[] | Yes | Executable + fixed args (no shell) |
| `commands.*.allow_extra_args` | bool | Yes | Whether caller can append args |
| `commands.*.cwd` | string | Yes | Working directory inside container |
| `commands.*.timeout` | int | No | Per-command timeout override |

## Logging

Every tool invocation is logged to `bridge.jsonl` with full request/response payloads:

```json
{
  "timestamp": "2026-04-01T14:22:05.123Z",
  "command": "run_tests",
  "args": ["--tb=short"],
  "exit_code": 0,
  "duration_ms": 2310,
  "stdout": "===== 68 passed in 2.31s =====\n",
  "stderr": "",
  "stdout_bytes": 35,
  "stderr_bytes": 0,
  "rejected": false,
  "rejection_reason": null
}
```

The log directory is volume-mounted from the host, so logs persist across container rebuilds.

## Development

Requires Docker. All commands are in the Makefile:

```bash
make help          # list available targets
make build         # build the dev image
make up            # start the bridge server (http://localhost:7357/mcp)
make down          # stop the bridge server
make logs          # tail server logs
make test          # run unit tests inside the container
make lint          # ruff check
make typecheck     # mypy
make format        # ruff format
make shell         # open a shell in the container
```

The bridge registers itself as an MCP server via `.mcp.json` (`bridge-dev` at `http://my-app:7357/mcp`). With the container running, Claude Code discovers and can call `echo_test`, `run_tests`, `run_lint`, `run_typecheck`, `run_format_check`, and `sleep_test` as tools for e2e verification.

## Removal

To remove the bridge from a project, delete these files — no application source code changes needed:

1. `commands.json`
2. `.mcp.json` (or `claude mcp remove dev-bridge`)
3. `docker-compose.dev.yml`
4. The `dev` stage from your Dockerfile
5. Bridge references from `doc/DEVELOPMENT.md`
6. `data/bridge-logs/` (optional, log data)

Your Makefile targets revert to `docker compose run --rm` behavior automatically.

## Documentation

- [Requirements](doc/REQUIREMENTS.md) — Functional requirements
- [Architecture](doc/ARCHITECTURE.md) — System design, deployment topology, integration model
- [Specifications](doc/SPECS.md) — MCP API contracts, config schemas, log format, consumer integration specs
- [Implementation Plan](doc/TODO.md) — Phased build plan with verification gates
- `doc/adr/` — Architecture Decision Records
