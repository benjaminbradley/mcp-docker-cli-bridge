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

Replace all `my-*` placeholders with names specific to your project.

| Placeholder | Meaning | Example |
|---|---|---|
| `my-app` | Docker Compose service name | `findworkbot`, `api`, `backend` |
| `my-app-dev-bridge-net` | Docker bridge network name | `fwb-dev-bridge-net`, `api-dev-bridge-net` |
| `my-app-bridge` | MCP server registration name | `fwb-bridge`, `api-bridge` |
| `172.my.subnet.0/24` | Fixed subnet for the bridge network | `172.22.0.0/24` |

### 1. Create the bridge network

Use a fixed subnet so your Claude Code devcontainer's firewall can allow it (see step 7):

```bash
docker network create --subnet=172.my.subnet.0/24 my-app-dev-bridge-net
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
    },
    "run_format_check": {
      "command": ["python", "-m", "ruff", "format", "--check", "src/"],
      "allow_extra_args": false,
      "cwd": "/app"
    },
    "run_format_fix": {
      "command": ["python", "-m", "ruff", "format", "src/"],
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
# Copy bridge server and install its dependencies
COPY bridge/server.py /bridge/server.py
COPY bridge/requirements.txt /bridge/requirements.txt
RUN pip install --no-cache-dir -r /bridge/requirements.txt \
    && mkdir -p /bridge/logs \
    && chown -R appuser:appuser /bridge
# Override app entrypoint — this container runs the bridge, not the app
ENTRYPOINT ["python", "/bridge/server.py"]
```

The `bridge/` files are provided to the Docker build via the `additional_contexts` directive in the compose overlay (step 4) — no changes to your main build context are needed.

### 4. Create a dev compose override

`docker-compose.dev.yml`:

```yaml
services:
  my-app:
    build:
      target: dev
      additional_contexts:
        bridge: ../mcp-docker-cli-bridge
    volumes:
      - ./commands.json:/bridge/commands.json:ro
      - ./data/bridge-logs:/bridge/logs
    networks:
      - default
      - my-app-dev-bridge-net
    expose:
      - "7357"

networks:
  my-app-dev-bridge-net:
    external: true
    name: ${BRIDGE_NETWORK:-my-app-dev-bridge-net}
```

### 5. Start the dev environment

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

The bridge server starts and logs the loaded commands:

```
Bridge listening on 0.0.0.0:7357
Loaded 5 commands: run_tests (timeout: 120s), run_lint (timeout: 60s), run_typecheck (timeout: 60s), run_format_check (timeout: 60s), run_format_fix (timeout: 60s)
```

### 6. Register with Claude Code

Add `.mcp.json` to your project root:

```json
{
  "mcpServers": {
    "my-app-bridge": {
      "type": "http",
      "url": "http://my-app:7357/mcp"
    }
  }
}
```

Or register via CLI:
```bash
claude mcp add --transport http my-app-bridge http://my-app:7357/mcp --scope local
```

Claude Code now discovers `run_tests`, `run_lint`, `run_typecheck`, `run_format_check`, and `run_format_fix` as tools and can call them autonomously.

### 7. Allow the bridge subnet in your Claude Code devcontainer firewall

Claude Code devcontainers typically run a network egress firewall. The devcontainer must allow the bridge network's subnet so that Claude Code can reach the bridge server.

Add this block to your project's `.devcontainer/init-firewall.sh`, **before** the `iptables -P INPUT DROP` line:

```bash
# Allow traffic to/from the bridge network (MCP server at my-app:7357)
BRIDGE_SUBNET="172.my.subnet.0/24"
echo "Allowing bridge subnet: $BRIDGE_SUBNET"
iptables -A INPUT -s "$BRIDGE_SUBNET" -j ACCEPT
iptables -A OUTPUT -d "$BRIDGE_SUBNET" -j ACCEPT
```

The subnet must match the one used in step 1. Use a different subnet per project to avoid conflicts between simultaneously running bridge networks.

After updating the firewall script, **rebuild the devcontainer** (VS Code: `Dev Containers: Rebuild Container`) to apply the change. Until then, you can apply it manually in the current session:

```bash
sudo iptables -A INPUT -s 172.my.subnet.0/24 -j ACCEPT
sudo iptables -A OUTPUT -d 172.my.subnet.0/24 -j ACCEPT
```

### 8. Connect the devcontainer to the bridge network

After each devcontainer rebuild, connect it to the bridge network from the host so that `my-app` resolves correctly inside the devcontainer:

```bash
# Find the devcontainer name
docker ps --format '{{.Names}}'

docker network connect my-app-dev-bridge-net <devcontainer-name>
```

After `make down && make up` cycles (without a devcontainer rebuild), this step does not need to be repeated.

### 9. Verify connectivity

From inside the devcontainer:

```bash
curl http://my-app:7357/mcp
```

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
make up            # start the bridge server
make down          # stop the bridge server
make logs          # tail server logs
make test          # run unit tests inside the container
make lint          # ruff check
make typecheck     # mypy
make format        # ruff format
make shell         # open a shell in the container
```

The bridge self-hosts for its own development: `.mcp.json` registers the bridge at `http://my-app:7357/mcp` so Claude Code can call `echo_test`, `run_tests`, `run_lint`, `run_typecheck`, `run_format_check`, `run_format_fix`, and `sleep_test` as tools for e2e verification. Follow the Quick Start steps above using the bridge project's own `commands.dev.json` and `docker-compose.yml`.

## Removal

To remove the bridge from a project, delete these files — no application source code changes needed:

1. `commands.json`
2. `.mcp.json` (or `claude mcp remove my-app-bridge`)
3. `docker-compose.dev.yml`
4. The `dev` stage from your Dockerfile
5. Bridge references from `doc/DEVELOPMENT.md`
6. `data/bridge-logs/` (optional, log data)
7. The bridge subnet rule from `.devcontainer/init-firewall.sh`

Your Makefile targets revert to `docker compose run --rm` behavior automatically.

## Documentation

- [Requirements](doc/REQUIREMENTS.md) — Functional requirements
- [Architecture](doc/ARCHITECTURE.md) — System design, deployment topology, integration model
- [Specifications](doc/SPECS.md) — MCP API contracts, config schemas, log format, consumer integration specs
- [Implementation Plan](doc/TODO.md) — Phased build plan with verification gates
- `doc/adr/` — Architecture Decision Records
