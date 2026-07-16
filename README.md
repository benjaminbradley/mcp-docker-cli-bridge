# MCP Docker CLI Bridge

An MCP (Model Context Protocol) server that gives AI development agents secure, controlled access to CLI commands inside a Docker container.

## Contents

- [What This Is](#what-this-is)
- [Key Properties](#key-properties)
- [Prerequisites](#prerequisites)
- [Published Image](#published-image)
- [Quick Start](#quick-start)
- [Configuration Reference](#configuration-reference)
- [Logging](#logging)
- [Security](#security)
- [Choosing a Subnet](#choosing-a-subnet)
- [Removal](#removal)
- [Contributing](#contributing)
- [Documentation](#documentation)
- [License](#license)

## What This Is

This project is designed for a specific development topology:

- **Claude Code** runs inside a [VS Code Dev Container](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) — an isolated Docker container with a restricted network egress firewall and no Docker socket access.
- **Your application** runs in a separate Docker container, managed by `docker compose`.
- **Claude Code needs to run commands inside the app container** — tests, linters, type checkers — but cannot use `docker exec` (no socket) and should not be given unrestricted shell access.

The bridge solves this by running a small MCP HTTP server inside the app container alongside your application. It reads a `commands.json` allow-list that you define, and exposes each allow-listed command as an MCP tool over Streamable HTTP. Claude Code discovers those tools automatically and calls them like any other MCP tool.

```
┌──────────────────────────────┐     ┌──────────────────────────────┐
│  VS Code Dev Container       │     │  App Container               │
│                              │     │                              │
│  Claude Code                 │     │  Your application            │
│      │                       │     │                              │
│      │  MCP over HTTP        │     │  MCP CLI Bridge (port 7357)  │
│      └──────────────────────▶│─────▶      │                       │
│                              │     │      ▼                       │
│  (no Docker socket access)   │     │  pytest, ruff, mypy, ...     │
└──────────────────────────────┘     └──────────────────────────────┘
                    shared Docker bridge network
```

Both containers communicate over a dedicated Docker bridge network. Claude Code never touches the Docker daemon, and the app container never exposes anything beyond the allow-listed commands.

## Key Properties

- **MCP native** — Allow-listed commands appear as MCP tools with typed schemas. Claude Code discovers and calls them automatically.
- **Security-first** — Named command recipes with a read-only allow-list config. `subprocess.run` with `shell=False`. Schema-enforced constraints prevent unauthorized arguments.
- **Output filtering** — Every tool accepts an optional `pipe` parameter: a safe subset of Unix pipe syntax (`2>&1 | grep [-EinABC] 'pat' | head/tail N`) parsed and applied by the bridge, never passed to a shell.
- **Result caching** — Pass `cache: true` to store full output and get a `cache_id` back. Re-filter the same output with a different `pipe` using only `cache_id`, without re-running the command.
- **Dev-only** — Multi-stage Dockerfile integration keeps the bridge out of production images.
- **Reusable** — Project-agnostic. Configure the command allow-list for any CLI-based project.

See [SECURITY.md](doc/SECURITY.md) for a full threat model analysis and security implications for different usage scenarios.

## Prerequisites

Before starting, confirm your environment matches:

- **Claude Code running inside a devcontainer.** This bridge is designed for the devcontainer topology described above. See the [Claude Code devcontainer setup guide](https://code.claude.com/docs/en/devcontainer) if you haven't set one up yet.
- **Docker and Docker Compose** on the host machine.
- **An existing multi-stage Dockerfile for your app** with a stage that already installs the dev tools your allow-list will invoke (e.g. `pytest`, `ruff`, etc for a python project). If you don't have such a stage today, you'll need to add one before Step 3.
- Permission to modify your project's `Dockerfile`, `docker-compose*.yml`, and `.devcontainer/init-firewall.sh`.

## Published Image

The bridge is published to GitHub Container Registry:

```
ghcr.io/benjaminbradley/mcp-docker-cli-bridge:latest
```

Use `latest` for the most recent release, or pin to a specific semver tag (`v0.1.0`, `v0.1`) if you need a reproducible build.

## Quick Start

Replace all `my-*` placeholders with names specific to your project. Pick your names before you start and substitute them consistently through every step.

| Placeholder | Meaning | Example |
|---|---|---|
| `my-app` | Docker Compose service name | `findworkbot`, `api`, `backend` |
| `my-app-dev-bridge-net` | Docker bridge network name | `fwb-dev-bridge-net`, `api-dev-bridge-net` |
| `my-app-bridge` | MCP server registration name | `fwb-bridge`, `api-bridge` |
| `W.X.Y.0/29` | Fixed /29 subnet for the bridge network | `172.22.0.0/29` |

See [Choosing a Subnet](#choosing-a-subnet) for how to pick `W.X.Y.0` safely.

### 1. Create the bridge network

Use a fixed /29 subnet so your Claude Code devcontainer's firewall can allow it precisely (see step 7):

```bash
docker network create --subnet=W.X.Y.0/29 my-app-dev-bridge-net
```

A /29 gives 8 addresses: the network address, the broadcast address, one gateway address (reserved by Docker for the host bridge interface), and five usable container slots — more than enough for any dev setup.

### 2. Define your command allow-list

Create `commands.json` in your project root. This is a **sample file with tooling for a python project**. Define your allow-list based on the specific needs of your project.

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

Add a new stage that extends your existing **dev image** — the one that already has the tools your allow-list invokes installed. The bridge itself is pulled from ghcr.io as a named `FROM` stage:

```dockerfile
# Pull the bridge image (pin to a version tag)
FROM ghcr.io/benjaminbradley/mcp-docker-cli-bridge:latest AS bridge

FROM dev AS dev-with-bridge
COPY --from=bridge /bridge/server.py /bridge/server.py
COPY --from=bridge /bridge/requirements.txt /bridge/requirements.txt
RUN pip install --no-cache-dir -r /bridge/requirements.txt \
    && mkdir -p /bridge/logs \
    && chown -R appuser:appuser /bridge
# Override app entrypoint — this container runs the bridge, not the app
ENTRYPOINT ["python", "/bridge/server.py"]
```

> **The container that runs the bridge must have every tool your `commands.json` references.** In the example above, `FROM dev AS dev-with-bridge` assumes your Dockerfile already has a `dev` stage where `pytest`, `ruff`, `mypy`, etc. are installed. If your dev tools live in a differently-named stage, substitute that stage name. If they aren't installed in any stage yet, add them first — otherwise the bridge will report `command not found` when Claude Code calls a tool.

The `bridge` stage fetches from the registry at build time — no local clone of this repo required. Replace `latest` with a specific tag (`v0.1.0`) if you need a reproducible build.

<details>
<summary>Alternative: use a local checkout of the bridge repo</summary>

If you want to develop against an unpublished version or pin to local source, use Docker's `additional_contexts` feature instead of a registry reference.

`Dockerfile`:

```dockerfile
FROM dev AS dev-with-bridge
# COPY --from=bridge pulls from the named context in docker-compose.dev.yml
COPY --from=bridge server.py /bridge/server.py
COPY --from=bridge requirements.txt /bridge/requirements.txt
RUN pip install --no-cache-dir -r /bridge/requirements.txt \
    && mkdir -p /bridge/logs \
    && chown -R appuser:appuser /bridge
ENTRYPOINT ["python", "/bridge/server.py"]
```

`docker-compose.dev.yml` (add `additional_contexts` to the build section):

```yaml
services:
  my-app:
    build:
      target: dev-with-bridge
      additional_contexts:
        bridge: ../mcp-docker-cli-bridge   # path to local bridge checkout
```

`additional_contexts: bridge:` registers the local directory as the named context. This makes `COPY --from=bridge` resolve to the local directory rather than a registry image.

</details>

### 4. Create a dev compose override

`docker-compose.dev.yml`:

```yaml
services:
  my-app:
    build:
      target: dev-with-bridge
    # Explicitly set entrypoint here as well as in the Dockerfile.
    # Compose file entrypoint values take precedence over Dockerfile ENTRYPOINT
    # instructions, so if your base docker-compose.yml sets entrypoint: for this
    # service, the Dockerfile's ENTRYPOINT will be silently ignored without this.
    entrypoint: ["python", "/bridge/server.py"]
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

### 7. Configure your Claude Code devcontainer firewall

Claude Code devcontainers typically run a network egress firewall. Add a block to your project's `.devcontainer/init-firewall.sh` that:

1. **Blocks the Docker bridge gateway** — Docker reserves the first address in the subnet (e.g. `W.X.Y.1`) for the host machine's bridge interface. Blocking it prevents the devcontainer from reaching host services through this path.
2. **Allows only the MCP port** on the remaining subnet addresses — containers on the bridge network can only be reached on port 7357 (or whatever `BRIDGE_PORT` you set).

Add this block **before** the `iptables -P INPUT DROP` line:

```bash
# ── MCP bridge: my-app-dev-bridge-net ────────────────────────────────────────
BRIDGE_SUBNET="W.X.Y.0/29"
BRIDGE_GATEWAY="W.X.Y.1"   # Docker reserves .1 for the host bridge interface
BRIDGE_PORT="7357"           # Change if you've set a custom BRIDGE_PORT
echo "Configuring MCP bridge rules (subnet: $BRIDGE_SUBNET, port: $BRIDGE_PORT)"

# Block the gateway — prevents devcontainer from reaching host services
iptables -A OUTPUT -d "$BRIDGE_GATEWAY" -j REJECT --reject-with icmp-host-prohibited
iptables -A INPUT  -s "$BRIDGE_GATEWAY" -j REJECT --reject-with icmp-host-prohibited

# Allow the MCP port to/from containers on the subnet only
# Return traffic (responses from the app) is handled by the ESTABLISHED,RELATED rule below
iptables -A OUTPUT -d "$BRIDGE_SUBNET" -p tcp --dport "$BRIDGE_PORT" -j ACCEPT
# ─────────────────────────────────────────────────────────────────────────────
```

The subnet and port values must match step 1 and your `BRIDGE_PORT` environment variable (default: `7357`).

After updating the firewall script, **rebuild the devcontainer** (VS Code: `Dev Containers: Rebuild Container`) to apply the change.

### 8. Connect the devcontainer to the bridge network

After each devcontainer rebuild, connect it to the bridge network from the host so that `my-app` resolves correctly inside the devcontainer:

```bash
# Find the devcontainer name
docker ps --format '{{.Names}}'

docker network connect my-app-dev-bridge-net <devcontainer-name>
```

After `make down && make up` cycles (without a devcontainer rebuild), this step does not need to be repeated.

### 9. Verify connectivity

From inside the devcontainer, make a simple request to the endpoint:

```bash
curl http://my-app:7357/mcp
```

You should see a JSON-RPC response beginning with `{"jsonrpc":` - it will probably be an error, but this JSON response indicates the connection IS WORKING and Claude Code should be able to connect to the MCP. A timeout or network error indicates the connection is not working and the containers still need to be added to the docker network.

## Configuration Reference

### Environment Variables (server settings)

| Variable | Default | Description |
|---|---|---|
| `BRIDGE_PORT` | `7357` | Port the MCP server listens on |
| `BRIDGE_HOST` | `0.0.0.0` | Bind address |
| `BRIDGE_COMMANDS_FILE` | `/bridge/commands.json` | Path to the allow-list config |
| `BRIDGE_LOG_DIR` | `/bridge/logs` | Directory for the JSONL audit log |
| `BRIDGE_LOG_FILE` | `bridge.jsonl` | Log file name |

### commands.json (command allow-list)

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

The log always captures the full, unfiltered output — even when a `pipe` filter was applied to the MCP response. This means the audit log is always complete regardless of what the caller requested.

The log directory is volume-mounted from the host, so logs persist across container rebuilds.

## Security

### What this setup enforces

- **No Docker socket access.** Claude Code cannot call `docker exec`, inspect containers, or affect anything outside the allow-listed commands. It has no path to the Docker daemon.
- **Named command allow-list.** Only commands declared in `commands.json` are callable. The set is fixed at server startup; there is no way to add commands at runtime.
- **Shell bypass prevented.** All commands run via `subprocess.run(shell=False)`. The executable and its fixed arguments are never passed through a shell interpreter.
- **Metacharacter blocklist.** Caller-supplied arguments are checked against a blocklist (`;`, `&&`, `|`, `$(`, `>`, `<`, etc.) before execution. Arguments containing any blocked sequence are rejected and logged.
- **Argument schema enforcement.** Commands with `allow_extra_args: false` expose no `args` parameter in the MCP tool schema — the MCP SDK rejects any call that tries to supply one.
- **Read-only allow-list.** `commands.json` is volume-mounted `:ro` — the bridge process cannot modify it.
- **Concurrency lock.** Only one command runs at a time. Concurrent calls receive an immediate error naming the in-progress command, preventing queue-based abuse.
- **Audit log.** Every invocation (including rejections) is logged with full arguments, exit code, stdout, stderr, and timing. Log entries are append-only from the server's perspective.
- **Non-root execution.** The bridge server runs as a non-root user inside the container.
- **Firewall port restriction.** With the recommended `init-firewall.sh` configuration, the devcontainer can only reach the bridge subnet on the single MCP port, and cannot reach the host machine via the Docker bridge gateway.

### Remaining gaps and limitations

- **No authentication on the MCP endpoint.** The bridge listens on plain HTTP with no token or credential requirement. Any container that can reach the bridge subnet on port 7357 can call any allow-listed tool. The firewall rules mitigate this by limiting which containers can reach the port, but there is no per-caller identity.
- **No TLS.** Traffic between Claude Code and the bridge is unencrypted. This is acceptable on a local Docker bridge network (traffic does not leave the host) but means the bridge should never be exposed on a routable network interface.
- **`allow_extra_args: true` commands accept argument-shaped input.** Shell injection is blocked, but a caller can still influence command behavior by crafting argv values (e.g., passing a different test path to pytest). Only allow-list commands with `allow_extra_args: true` where argument variance is intentional.
- **Subprocess resource usage is uncapped.** Timeouts prevent indefinite hangs, but a allow-listed command can consume significant CPU or memory during its allowed window. This is inherent to any test-runner integration.
- **Audit log is not tamper-proof.** The JSONL file is append-only from the server's perspective, but it is a plain file on a volume mount — a process with filesystem access can modify it.
- **Shared container filesystem.** The bridge runs in the same container as your application and has access to the same filesystem. It is not a sandbox; it can read application source, config, and data files. This is by design (it needs to run tools against your code), but it means the bridge's attack surface is the container's full filesystem, not just the allow-listed commands.

## Choosing a Subnet

Each bridge network needs a dedicated subnet so the devcontainer firewall can allow exactly that network's traffic. This section explains how to pick one that won't conflict with your existing setup or other simultaneously running projects.

### Why a fixed subnet is required

Docker can assign subnets automatically, but the devcontainer firewall script runs at container startup — before the bridge network necessarily exists. A fixed subnet lets you write a firewall rule that will be valid regardless of startup order.

### Subnet size: use /29

A /29 gives 8 addresses:

| Address | Role |
|---|---|
| `W.X.Y.0` | Network address (unusable) |
| `W.X.Y.1` | Docker bridge gateway — host machine's bridge interface |
| `W.X.Y.2` – `W.X.Y.6` | Available for containers (5 slots) |
| `W.X.Y.7` | Broadcast address (unusable) |

Five container slots is sufficient for any realistic dev environment running the bridge. If you somehow need more, use a /28 (14 usable addresses).

### Picking a safe base address

Work through this checklist:

**1. Check what Docker networks already exist on your machine:**

```bash
docker network ls -q | xargs docker network inspect \
  --format '{{.Name}}: {{range .IPAM.Config}}{{.Subnet}}{{end}}'
```

Note all the subnets in use. Your new /29 must not overlap any of them.

**2. Check your host's routing table for VPN or physical network ranges:**

```bash
ip route
```

Corporate VPNs frequently claim large blocks of `10.0.0.0/8` or `172.16.0.0/12`. If your VPN owns `172.20.0.0/14`, for example, you need to stay outside that range entirely.

**3. Pick from a low-traffic zone of the private address space:**

The `172.16.0.0/12` range (`172.16.0.0` – `172.31.255.255`) is standard for Docker but also commonly grabbed by VPNs. If you're on a VPN that owns a wide block here, prefer `10.255.0.0/8` (the far end of the 10/8 space, least commonly assigned by VPNs and routers) or `192.168.200.0/24` and above.

**4. Assign subnets systematically if you run multiple simultaneous projects:**

Each project that uses the bridge needs its own /29. A simple scheme — increment by 8 per project within a reserved /24:

| Project | Network name | Subnet |
|---|---|---|
| my-project | `myproj-dev-bridge-net` | `172.22.0.0/29` |
| my-api | `api-dev-bridge-net` | `172.22.0.8/29` |
| my-frontend | `fe-dev-bridge-net` | `172.22.0.16/29` |
| … | … | … |

Choosing a single /24 base (here `172.22.0.0/24`) for all your bridge networks means one block to check for conflicts, and the increments are easy to track.

**5. Document your allocation.**

Add a comment to each project's `.devcontainer/init-firewall.sh` naming the subnet and its source, so future you knows why `172.22.0.0/29` was chosen and doesn't accidentally reuse it.

### Creating the network with the chosen subnet

```bash
docker network create --subnet=W.X.Y.0/29 my-app-dev-bridge-net
```

Verify it was created correctly:

```bash
docker network inspect my-app-dev-bridge-net \
  --format '{{range .IPAM.Config}}Subnet: {{.Subnet}}, Gateway: {{.Gateway}}{{end}}'
```

The gateway shown will be `W.X.Y.1` — this is the address to block in the firewall script (step 7 of Quick Start).

## Removal

To remove the bridge from a project, delete these files — no application source code changes needed:

1. `commands.json`
2. `.mcp.json` (or `claude mcp remove my-app-bridge`)
3. `docker-compose.dev.yml`
4. The `dev-with-bridge` stage from your Dockerfile
5. Any references to the bridge in your project docs
6. `data/bridge-logs/` (optional, log data)
7. The bridge subnet block from `.devcontainer/init-firewall.sh`

Your Makefile targets revert to `docker compose run --rm` behavior automatically.

## Contributing

**Working on the bridge itself?** See [CONTRIBUTING.md](CONTRIBUTING.md) for repo layout, dev commands, dependency locking, and a description of the CI/CD pipeline that scans, builds, and publishes this project.

## Original Build Documentation

- [Requirements](doc/REQUIREMENTS.md) — Functional requirements
- [Architecture](doc/ARCHITECTURE.md) — System design, deployment topology, integration model
- [Specifications](doc/SPECS.md) — MCP API contracts, config schemas, log format, consumer integration specs
- [Initial Build Plan](doc/buildlog/INITIAL-BUILD-PLAN.md) — Phased build plan with verification gates (archived)
- `doc/adr/` — Architecture Decision Records

## License

MIT — see [LICENSE](LICENSE).
