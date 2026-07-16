# Architecture — MCP Docker CLI Bridge

> **Status:** Approved
> **Last updated:** 2026-04-01
> **References:** [ADR 001 — MCP Transport](adr/001-mcp-transport.md) · [ADR 002 — Pydantic Models](adr/002-pydantic-models.md)

---

## 1. System Overview

The bridge is a single-process MCP server that exposes allowlisted CLI commands as MCP tools over Streamable HTTP transport. It runs inside a host project's Docker container during development, reachable only on an internal Docker bridge network.

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
│  │                      │network │  │  Allowlist   Executor  │  │ │
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
│    ./commands.json     → /bridge/commands.json (allowlist, ro)   │
│    ./data/bridge-logs/ → /bridge/logs/      (JSONL audit, rw)   │
│                                                                  │
│  External network:                                               │
│    <project-bridge-net>  (created once, shared, not compose-     │
│                           managed)                               │
└──────────────────────────────────────────────────────────────────┘
```

The Controller (Claude Code) connects to the bridge as a standard MCP client. It discovers available tools via `tools/list` and invokes them via `tools/call`. The bridge translates each tool call into a subprocess invocation constrained by the read-only command allowlist.

The human operator bypasses the bridge entirely, using `make` targets that `docker compose exec` into the running container or `docker compose run --rm` ephemeral containers.

---

## 2. Bridge Server Components

The server is a single Python file (`server.py`) using the MCP Python SDK for the transport layer, pydantic for data validation and serialization, and Python stdlib for command execution. It has six internal responsibilities:

### 2.1 MCP Tool Provider

Uses the MCP Python SDK to register tools and handle Streamable HTTP transport. On startup, the server reads the command allowlist and registers each command as an MCP tool with a typed input schema. The SDK handles protocol negotiation, request routing, and response serialization.

Tools are registered dynamically from the allowlist — the server code does not hardcode any tool definitions. Adding a new command to `commands.json` and restarting the container is sufficient.

Tool schemas are derived from the allowlist:
- Commands with `allow_extra_args: true` get an input schema with an optional `args` array parameter.
- Commands with `allow_extra_args: false` get an input schema with no parameters. The protocol-level constraint prevents the Controller from sending arguments.

### 2.2 Concurrency Guard

An `asyncio.Lock` that ensures only one command executes at a time. Each tool handler attempts a non-blocking acquire before execution. If the lock is already held, the handler immediately returns an `isError: true` result naming the in-progress command and telling the client to retry. The currently executing command name is tracked in a module-level variable, set on acquire and cleared on release. No queuing or blocking — rejection is instantaneous.

### 2.3 Allowlist Loader

Reads `commands.json` once at startup and validates it against pydantic models (`CommandsConfig` containing `CommandEntry` instances). The config includes a global `default_timeout` and per-command entries that may override it. Invalid config — missing fields, wrong types, empty command arrays — fails with pydantic's field-level error messages and exits the server immediately. There is no hot-reload — changing the allowlist requires a container restart.

### 2.4 Executor

Resolves a command name to its allowlist entry, constructs the full argument vector (executable prefix + optional caller args), and calls `subprocess.run` with `shell=False`, `capture_output=True`, `text=True`, the command's effective timeout, and `cwd` from the allowlist entry. Returns a typed `CommandResult` (stdout, stderr, exit_code). Catches `subprocess.TimeoutExpired` and `FileNotFoundError` and translates them to MCP tool errors.

### 2.5 Argument Validator

A pure function called before execution. Checks that all caller-provided arguments are strings and do not contain shell metacharacters. This is defense-in-depth — `shell=False` already prevents injection — but rejects clearly malformed input early with a descriptive error.

### 2.6 Request Logger

Constructs a `LogEntry` pydantic model per tool invocation and appends its JSON serialization (`model_dump_json()`) as a single line to a JSONL log file. Each entry includes full request and response payloads (command, args, stdout, stderr) alongside metadata (timestamp, exit code, duration, byte lengths, rejection status). This provides a complete audit trail for debugging and analysis. Concurrency rejections are logged with a "busy" rejection reason.

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
    │                                  │  0. Acquire concurrency lock  │
    │                                  │     (non-blocking; if busy    │
    │                                  │      → reject immediately)    │
    │                                  │  1. Look up "run_tests"       │
    │                                  │     in allowlist               │
    │                                  │  2. Validate args             │
    │                                  │  3. Build argv:               │
    │                                  │     ["python","-m","pytest",  │
    │                                  │      "--tb=short"]            │
    │                                  │  4. subprocess.run(argv,      │
    │                                  │     shell=False, cwd="/app",  │
    │                                  │     timeout=120)              │
    │                                  │─────────────────────────────▶│
    │                                  │                               │
    │                                  │  stdout, stderr, returncode  │
    │                                  │◀─────────────────────────────│
    │                                  │  5. Log full result (JSONL)  │
    │                                  │  6. Release concurrency lock │
    │                                  │  7. Return tool result       │
    │  content: [{text: JSON of        │                               │
    │    stdout, stderr, exit_code}]   │                               │
    │◀─────────────────────────────────│                               │
```

Error paths short-circuit at the relevant step: busy at step 0, unknown command at step 1, metacharacter rejection at step 2, timeout or exec failure at step 4. All paths log (step 5) and release the lock (step 6, via finally/context manager). Bridge-level errors set `isError: true` in the MCP tool result.

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

The `base` stage is the production image. The `dev` stage extends it. The bridge file and its MCP SDK dependencies never appear in production builds.

### 4.2 Compose Override (in host project)

The host project provides a `docker-compose.dev.yml` that targets the `dev` stage of the Dockerfile, keeps the container running (bridge server as entrypoint), mounts the commands allowlist read-only, mounts the log directory read-write, attaches to the external bridge network, and exposes port 7357 on the bridge network only (no host port binding).

The base `docker-compose.yml` is unchanged. The dev override is additive.

### 4.3 External Bridge Network

Created once by the operator: `docker network create <network-name>`. Not managed by any project's compose lifecycle. Both the Controller container and the Target container (via their respective compose configs) attach to this network. The network name is a per-deployment convention, documented in each consumer project.

### 4.4 Controller MCP Registration

The Controller (Claude Code) is configured to connect to the bridge as an MCP server via a `.mcp.json` file at the consumer project root or a CLI command (`claude mcp add`). The registration tells Claude Code where to find the bridge. Tool discovery and invocation happen automatically via the MCP protocol.

---

## 5. Integration Model

The bridge project is a **sibling directory dependency** — it lives alongside consumer projects on the host filesystem, not inside them.

```
parent/
├── mcp-docker-cli-bridge/       # This project (shared tool)
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
├── example-app/                 # Consumer project
│   ├── commands.json            # Project-specific allowlist
│   ├── .mcp.json                # MCP registration for CC
│   ├── docker-compose.dev.yml   # Dev override referencing bridge
│   ├── doc/DEVELOPMENT.md       # Documents bridge dependency
│   └── ...
│
└── other-project/               # Another consumer
    ├── commands.json
    ├── .mcp.json
    ├── docker-compose.dev.yml
    └── ...
```

Each consumer provides: `commands.json` (allowlist, mounted read-only), `docker-compose.dev.yml` (dev overlay), a Dockerfile `dev` stage, `.mcp.json` (MCP registration), and documentation (`doc/DEVELOPMENT.md`). Optionally: a pre-commit hook and Makefile dual-mode targets.

---

## 6. Data Model

The bridge has no persistent data model. Its runtime data structures are defined as pydantic models (see SPECS.md §6.1 for definitions):

### 6.1 Allowlist Configuration

`CommandsConfig` — the entire `commands.json` file: global `default_timeout` plus a dict of `CommandEntry` instances. Each `CommandEntry` defines the executable prefix, extra-args toggle, working directory, and optional per-command timeout override. Validated by pydantic on load.

### 6.2 Command Result (transient, per invocation)

`CommandResult` — subprocess execution output: `stdout`, `stderr`, `exit_code`. Serialized to JSON for the MCP tool result text field.

### 6.3 Log Entry (appended to JSONL file)

`LogEntry` — per-request record: timestamp, command, args, exit code, duration, full stdout/stderr content, byte lengths, rejection status. Serialized via `model_dump_json()` and appended to the log file.

### 6.4 Server Configuration

`BridgeConfig` — server settings loaded from `BRIDGE_*` environment variables with defaults. Validated at startup.

---

## 7. Security Boundaries

The bridge's security posture is designed for a trusted dev-only network, not hostile environments.

- **Network isolation:** The bridge port is reachable only from the Docker bridge network. No host port binding by default.
- **Command restriction:** Only allowlisted commands execute. The allowlist file is mounted read-only.
- **Schema-enforced constraints:** Commands with `allow_extra_args: false` generate tool schemas with no args parameter. The protocol-level constraint prevents the Controller from sending arguments.
- **No shell:** `subprocess.run` with `shell=False` eliminates the shell injection surface entirely.
- **Argument validation:** Defense-in-depth rejection of shell metacharacters in caller-provided args.
- **No auth:** Intentional. Network isolation is the access control. Adding auth would increase complexity without meaningful security improvement in the dev context.
- **No file transfer:** The bridge does not read or write files on behalf of the caller. Filesystem access happens through volume mounts, orthogonal to the bridge.

---

## 8. Constraints and Dependencies

- **Python MCP SDK + pydantic.** The server depends on the `mcp` package (which transitively installs pydantic, starlette, uvicorn). The bridge imports from both `mcp` and `pydantic` directly. Dependencies are declared in `requirements.txt` and installed in the dev Docker stage. See ADR 002 for rationale.
- **Serialized tool execution.** One command at a time, enforced by an `asyncio.Lock`. Concurrent requests are rejected immediately with a retry message — no queuing, no blocking. This prevents subprocess resource contention and keeps the execution model predictable.
- **No hot-reload.** Allowlist changes require a container restart. This prevents runtime config mutation.
- **Docker required.** The bridge assumes it runs inside a Docker container on a Docker bridge network. It has no standalone mode.
- **Consumer provides the Dockerfile.** The bridge project ships `server.py` and `requirements.txt`. The consumer project owns the Dockerfile, compose files, allowlist, MCP registration, and all integration wiring.
