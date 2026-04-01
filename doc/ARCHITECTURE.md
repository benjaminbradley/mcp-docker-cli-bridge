# Architecture — Docker CLI Access Bridge MCP

> **Status:** Approved
> **Last updated:** 2026-04-01
> **References:** [ADR 001 — MCP Transport](adr/001-mcp-transport.md) · [ADR 002 — Pydantic Models](adr/002-pydantic-models.md)

---

## 1. System Overview

The bridge is a single-process MCP server that exposes whitelisted CLI commands as MCP tools over Streamable HTTP transport. It runs inside a host project's Docker container during development, reachable only on an internal Docker bridge network.

```
┌──────────────────────────────────────────────────────────────────┐
│  Host Machine                                                    │
│                                                                  │
│  ┌──────────────────────┐       ┌──────────────────────────────┐ │
│  │ Controller Container │       │ Target Container (dev stage) │ │
│  │ (Claude Code)        │       │                              │ │
│  │                      │       │  ┌────────────────────────┐  │ │
│  │  MCP Client ─────────┼──────▶│  │ Bridge MCP Server      │  │ │
│  │  (tools/list,        │  Docker│  │ (:7357/mcp)            │  │ │
│  │   tools/call)        │  bridge│  │                        │  │ │
│  │                      │network │  │  Whitelist   Executor  │  │ │
│  │  Volume: /app/src ───┼───────┼──│  Loader      ─────────▶│──┼─┤ subprocess.run
│  │  (shared source)     │       │  │               Validator │  │ │ (shell=False)
│  │                      │       │  │               Logger    │  │ │
│  └──────────────────────┘       │  └────────────────────────┘  │ │
│                                  │                              │ │
│                                  │  Application code + dev tools│ │
│                                  │  (pytest, ruff, mypy, etc.)  │ │
│                                  └──────────────────────────────┘ │
│                                                                  │
│  Volumes:                                                        │
│    ./src/              → /app/src/          (source code, rw)    │
│    ./commands.json     → /bridge/commands.json (whitelist, ro)   │
│    ./data/bridge-logs/ → /bridge/logs/      (JSONL audit, rw)   │
│                                                                  │
│  External network:                                               │
│    <project-bridge-net>  (created once, shared, not compose-     │
│                           managed)                               │
└──────────────────────────────────────────────────────────────────┘
```

The Controller (Claude Code) connects to the bridge as a standard MCP client. It discovers available tools via `tools/list` and invokes them via `tools/call`. The bridge translates each tool call into a subprocess invocation constrained by the read-only command whitelist.

The human operator bypasses the bridge entirely, using `make` targets that `docker compose exec` into the running container or `docker compose run --rm` ephemeral containers.

---

## 2. Bridge Server Components

The server is a single Python file (`server.py`) using the MCP Python SDK for the transport layer, pydantic for data validation and serialization, and Python stdlib for command execution. It has five internal responsibilities:

### 2.1 MCP Tool Provider

Uses the MCP Python SDK to register tools and handle Streamable HTTP transport. On startup, the server reads the command whitelist and registers each command as an MCP tool with a typed input schema. The SDK handles protocol negotiation, request routing, and response serialization.

Tools are registered dynamically from the whitelist — the server code does not hardcode any tool definitions. Adding a new command to `commands.json` and restarting the container is sufficient.

Tool schemas are derived from the whitelist:
- Commands with `allow_extra_args: true` get an input schema with an optional `args` array parameter.
- Commands with `allow_extra_args: false` get an input schema with no parameters. The protocol-level constraint prevents the Controller from sending arguments.

### 2.2 Whitelist Loader

Reads `commands.json` once at startup and validates it against a pydantic model (`CommandsConfig` containing `CommandEntry` instances). Invalid config — missing fields, wrong types, empty command arrays — fails with pydantic's field-level error messages and exits the server immediately. There is no hot-reload — changing the whitelist requires a container restart.

### 2.3 Executor

Resolves a command name to its whitelist entry, constructs the full argument vector (executable prefix + optional caller args), and calls `subprocess.run` with `shell=False`, `capture_output=True`, `text=True`, `timeout`, and `cwd` from the whitelist entry. Returns a typed `CommandResult` (stdout, stderr, exit_code). Catches `subprocess.TimeoutExpired` and `FileNotFoundError` and translates them to MCP tool errors.

### 2.4 Argument Validator

A pure function called before execution. Checks that all caller-provided arguments are strings and do not contain shell metacharacters. This is defense-in-depth — `shell=False` already prevents injection — but rejects clearly malformed input early with a descriptive error.

### 2.5 Request Logger

Constructs a `LogEntry` pydantic model per tool invocation and appends its JSON serialization (`model_dump_json()`) as a single line to a JSONL log file. The entry is written after the request completes (or fails), capturing metadata only: timestamp, command name, args, exit code, duration in milliseconds, stdout/stderr byte lengths, and rejection reason if applicable. Stdout/stderr content is not logged.

The logger opens and closes the file per write (append mode) to avoid holding file handles and to ensure log entries are flushed even if the server crashes.

---

## 3. Request Flow

```
Controller (CC)                   Bridge MCP Server                subprocess
    │                                  │                               │
    │  tools/list                      │                               │
    │─────────────────────────────────▶│                               │
    │  [{name:"run_tests",             │                               │
    │    inputSchema:{args:[str]}},    │                               │
    │   {name:"run_lint",              │                               │
    │    inputSchema:{}}]              │                               │
    │◀─────────────────────────────────│                               │
    │                                  │                               │
    │  tools/call                      │                               │
    │  name:"run_tests"                │                               │
    │  args:["--tb=short"]             │                               │
    │─────────────────────────────────▶│                               │
    │                                  │  1. Look up "run_tests"       │
    │                                  │     in whitelist               │
    │                                  │  2. Validate args             │
    │                                  │  3. Build argv:               │
    │                                  │     ["python","-m","pytest",  │
    │                                  │      "--tb=short"]            │
    │                                  │  4. subprocess.run(argv,      │
    │                                  │     shell=False, cwd="/app")  │
    │                                  │─────────────────────────────▶│
    │                                  │                               │
    │                                  │  stdout, stderr, returncode  │
    │                                  │◀─────────────────────────────│
    │                                  │  5. Log metadata (JSONL)     │
    │                                  │  6. Return tool result       │
    │  content: [{text: JSON of        │                               │
    │    stdout, stderr, exit_code}]   │                               │
    │◀─────────────────────────────────│                               │
```

Error paths short-circuit at the relevant step: unknown command at step 1 (tool not found), metacharacter rejection at step 2, timeout or exec failure at step 4. All error paths still log (step 5) with the rejection reason. Bridge-level errors set `isError: true` in the MCP tool result.

---

## 4. Deployment Topology

### 4.1 Multi-stage Dockerfile (in host project)

The bridge integrates into the host project's Dockerfile as an additional build stage. The bridge server file and its dependencies are copied from the sibling project directory at build time.

```
FROM python:3.x AS base
# ... application setup, production dependencies ...

FROM base AS dev
# ... dev dependencies (pytest, ruff, mypy) ...
COPY bridge/server.py /bridge/server.py
COPY bridge/requirements.txt /bridge/requirements.txt
RUN pip install --no-cache-dir -r /bridge/requirements.txt
CMD ["python", "/bridge/server.py"]
```

The `base` stage is the production image. The `dev` stage extends it. The bridge file and its MCP SDK dependencies never appear in production builds. The exact `COPY` path depends on the Docker build context; the host project's compose override configures this.

### 4.2 Compose Override (in host project)

The host project provides a `docker-compose.dev.yml` that:
- Targets the `dev` stage of the Dockerfile.
- Keeps the container running (bridge server as entrypoint).
- Mounts the commands whitelist read-only.
- Mounts the log directory read-write.
- Attaches to the external bridge network.
- Exposes port 7357 on the bridge network only (no host port binding).

The base `docker-compose.yml` is unchanged. The dev override is additive.

### 4.3 External Bridge Network

Created once by the operator: `docker network create <network-name>`. Not managed by any project's compose lifecycle. Both the Controller container and the Target container (via their respective compose configs) attach to this network. The network name is a per-deployment convention, documented in each consumer project.

### 4.4 Controller MCP Registration

The Controller (Claude Code) is configured to connect to the bridge as an MCP server. This is done via one of:
- A `.mcp.json` file at the consumer project root (version-controllable, project-scoped).
- A CLI command: `claude mcp add --transport http dev-bridge http://<service>:7357/mcp`.

The registration tells Claude Code where to find the bridge. Tool discovery and invocation happen automatically via the MCP protocol.

---

## 5. Integration Model

The bridge project is a **sibling directory dependency** — it lives alongside consumer projects on the host filesystem, not inside them.

```
parent/
├── mcp-docker-cli-bridge/    # This project (shared tool)
│   ├── server.py                # The bridge MCP server
│   ├── requirements.txt         # MCP SDK + dependencies
│   ├── README.md
│   └── doc/
│       ├── REQUIREMENTS.md
│       ├── ARCHITECTURE.md
│       ├── SPECS.md
│       ├── TODO.md
│       └── adr/
│           ├── 001-mcp-transport.md
│           └── 002-pydantic-models.md
│
├── example-app/               # Consumer project A
│   ├── commands.json            # FWB-specific whitelist
│   ├── .mcp.json                # MCP registration for CC
│   ├── docker-compose.dev.yml   # Dev override referencing bridge
│   ├── doc/DEVELOPMENT.md       # Documents bridge dependency
│   └── ...
│
└── other-project/               # Consumer project B
    ├── commands.json            # Its own whitelist
    ├── .mcp.json                # Its own MCP registration
    ├── docker-compose.dev.yml   # Its own dev override
    └── ...
```

Each consumer provides these integration touchpoints:

1. **`commands.json`** — the project-specific command whitelist, mounted read-only into the dev container.
2. **`docker-compose.dev.yml`** — dev compose override that builds the dev stage, mounts the whitelist and logs, and joins the bridge network.
3. **Dockerfile dev stage** — extends the production image with dev tools, the bridge server, and its dependencies.
4. **`.mcp.json`** — registers the bridge as an MCP server for Claude Code.
5. **Documentation** — `doc/DEVELOPMENT.md` for humans.

Optional:
6. **Pre-commit hook** — script that calls the bridge for lint/typecheck/test checks.
7. **Makefile dual-mode** — targets that detect the running dev container and use `exec` instead of `run --rm`.

---

## 6. Data Model

The bridge has no persistent data model. Its runtime data structures are defined as pydantic models (see SPECS.md §6.1 for definitions):

### 6.1 Whitelist Entry (in-memory, loaded from commands.json)

`CommandEntry` — per-command configuration read at startup: command name (dict key), executable prefix (`command`), extra args toggle (`allow_extra_args`), and working directory (`cwd`). Validated by pydantic on load; invalid config exits the server with detailed field-level errors.

### 6.2 Command Result (transient, per invocation)

`CommandResult` — subprocess execution output: `stdout`, `stderr`, `exit_code`. Serialized to JSON for the MCP tool result text field.

### 6.3 Log Entry (appended to JSONL file)

`LogEntry` — per-request metadata: timestamp, command, args, exit code, duration, stdout/stderr byte lengths, rejection status. Serialized via `model_dump_json()` and appended to the log file.

### 6.4 Server Configuration

`BridgeConfig` — server settings loaded from `BRIDGE_*` environment variables with defaults. Validated at startup.

---

## 7. Security Boundaries

The bridge's security posture is designed for a trusted dev-only network, not hostile environments.

- **Network isolation:** The bridge port is reachable only from the Docker bridge network. No host port binding by default.
- **Command restriction:** Only whitelisted commands execute. The whitelist file is mounted read-only.
- **Schema-enforced constraints:** Commands with `allow_extra_args: false` generate tool schemas with no args parameter. The protocol-level constraint prevents the Controller from sending arguments.
- **No shell:** `subprocess.run` with `shell=False` eliminates the shell injection surface entirely.
- **Argument validation:** Defense-in-depth rejection of shell metacharacters in caller-provided args.
- **No auth:** Intentional. Network isolation is the access control. Adding auth would increase complexity without meaningful security improvement in the dev context.
- **No file transfer:** The bridge does not read or write files on behalf of the caller. Filesystem access happens through volume mounts, orthogonal to the bridge.

---

## 8. Constraints and Dependencies

- **Python MCP SDK + pydantic.** The server depends on the `mcp` package (which transitively installs pydantic, starlette, uvicorn). The bridge imports from both `mcp` and `pydantic` directly. Dependencies are declared in `requirements.txt` and installed in the dev Docker stage. See ADR 002 for the rationale on using pydantic.
- **Single-threaded tool execution.** One command at a time. The MCP SDK may handle concurrent transport-level requests, but tool execution is serialized. Sufficient for sequential dev tool invocations.
- **No hot-reload.** Whitelist changes require a container restart. This is a feature — it prevents runtime config mutation.
- **Docker required.** The bridge assumes it runs inside a Docker container on a Docker bridge network. It has no standalone mode.
- **Consumer provides the Dockerfile.** The bridge project ships `server.py` and `requirements.txt`. The consumer project owns the Dockerfile, compose files, whitelist, MCP registration, and all integration wiring.
