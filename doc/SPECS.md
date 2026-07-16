# Specifications — MCP Docker CLI Bridge

> **Status:** Approved
> **Last updated:** 2026-06-02
> **References:** [Requirements](REQUIREMENTS.md) · [Architecture](ARCHITECTURE.md) · [ADR 001](adr/001-mcp-transport.md) · [ADR 002](adr/002-pydantic-models.md)

---

## 1. MCP Server Interface

### 1.1 Transport

The bridge uses Streamable HTTP transport as defined by MCP spec version 2025-03-26. The server exposes a single MCP endpoint:

```
POST /mcp
GET  /mcp
```

The MCP Python SDK handles protocol negotiation, JSON-RPC framing, and session management. The bridge code registers tools and handles tool calls; the SDK handles everything else.

### 1.2 Tool Discovery (tools/list)

On `tools/list`, the server returns one tool per allowlist entry. Tool definitions are generated dynamically from `commands.json` at startup.

Example response (for a allowlist with three commands):

```json
{
  "tools": [
    {
      "name": "run_tests",
      "description": "Execute: python -m pytest src/tests/ -v",
      "inputSchema": {
        "type": "object",
        "properties": {
          "args": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Additional arguments appended to the command"
          },
          "pipe": {
            "type": "string",
            "description": "Filter output: 2>&1 | grep [-EinABC] 'pat' | head/tail N. Example: \"2>&1 | grep -iA 5 'FAILED' | tail 100\""
          },
          "cache": {
            "type": "boolean",
            "description": "Cache full output; returns cache_id for reuse"
          },
          "cache_id": {
            "type": "string",
            "description": "UUID from prior result — skips re-execution, applies pipe to cached output"
          }
        }
      }
    },
    {
      "name": "run_lint",
      "description": "Execute: python -m ruff check src/",
      "inputSchema": {
        "type": "object",
        "properties": {
          "pipe": {
            "type": "string",
            "description": "Filter output: 2>&1 | grep [-EinABC] 'pat' | head/tail N. Example: \"2>&1 | grep -iA 5 'FAILED' | tail 100\""
          },
          "cache": {
            "type": "boolean",
            "description": "Cache full output; returns cache_id for reuse"
          },
          "cache_id": {
            "type": "string",
            "description": "UUID from prior result — skips re-execution, applies pipe to cached output"
          }
        }
      }
    },
    {
      "name": "run_typecheck",
      "description": "Execute: python -m mypy src/",
      "inputSchema": {
        "type": "object",
        "properties": {
          "pipe": {
            "type": "string",
            "description": "Filter output: 2>&1 | grep [-EinABC] 'pat' | head/tail N. Example: \"2>&1 | grep -iA 5 'FAILED' | tail 100\""
          },
          "cache": {
            "type": "boolean",
            "description": "Cache full output; returns cache_id for reuse"
          },
          "cache_id": {
            "type": "string",
            "description": "UUID from prior result — skips re-execution, applies pipe to cached output"
          }
        }
      }
    }
  ]
}
```

Key behaviors:

- Commands with `allow_extra_args: true` include an `args` property in the schema.
- Commands with `allow_extra_args: false` have no `args` parameter — only `pipe`, `cache`, and `cache_id` are exposed.
- `pipe`, `cache`, and `cache_id` are present in every tool's schema regardless of `allow_extra_args`.
- The `description` is auto-generated from the executable prefix: `"Execute: "` + the command array joined by spaces.

### 1.3 Tool Invocation (tools/call)

**Request** (MCP JSON-RPC, handled by SDK):
```json
{
  "name": "run_tests",
  "arguments": {
    "args": ["--tb=short", "-x"]
  }
}
```

Optional filtering and caching parameters may also be supplied:
```json
{
  "name": "run_tests",
  "arguments": {
    "args": ["--tb=short"],
    "pipe": "2>&1 | grep -E 'FAILED|ERROR' | head 50",
    "cache": true
  }
}
```

**Success result** (subprocess completed, any exit code):
```json
{
  "content": [
    {
      "type": "text",
      "text": "{\"stdout\": \"===== 68 passed in 2.31s =====\\n\", \"stderr\": \"\", \"exit_code\": 0}"
    }
  ],
  "isError": false
}
```

When `pipe` or `cache` parameters are used, the `CommandResult` JSON may include additional fields:
```json
{
  "stdout": "FAILED test_foo.py::test_bar\nERROR test_baz.py::test_qux\n",
  "stderr": "",
  "exit_code": 1,
  "warnings": ["grep: flag -v not supported, ignored"],
  "cache_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

Fields `warnings`, `cache_id`, and `cache_age_ms` are omitted from the JSON entirely when `None` (serialized with `exclude_none=True`), so a plain call with no `pipe`/`cache` returns the same three-field shape as before.

The `text` field contains a `CommandResult` model serialized to JSON (see §6.1). Non-zero exit codes still produce `isError: false` — the bridge faithfully reports what the subprocess returned.

**Error result** (bridge-level failure):
```json
{
  "content": [
    {
      "type": "text",
      "text": "Command 'run_tests' timed out after 120s"
    }
  ],
  "isError": true
}
```

**Busy result** (concurrent execution rejected):
```json
{
  "content": [
    {
      "type": "text",
      "text": "Bridge is busy executing 'run_tests'. Retry after it completes."
    }
  ],
  "isError": true
}
```

Bridge-level errors that set `isError: true`:

- Concurrency rejection (another command is already running). The error message names the in-progress command and tells the client to retry.
- Argument validation failure (metacharacter detected).
- Command timeout (`subprocess.TimeoutExpired`).
- Subprocess execution failure (`FileNotFoundError` — executable not found).
- Unknown tool name (should not normally occur since `tools/list` advertises only valid tools, but handled defensively).

### 1.4 Unsupported MCP Features

The bridge does not implement Resources, Prompts, Sampling, or Resource Subscriptions. Requests for these capabilities receive standard MCP "method not found" responses from the SDK.

---

## 2. Command Allowlist Schema (commands.json)

### 2.1 File Format

A JSON object with a `default_timeout` field and a `commands` object where each key is a command name and each value is a command definition.

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
    "run_format": {
      "command": ["python", "-m", "ruff", "format", "src/"],
      "allow_extra_args": false,
      "cwd": "/app"
    }
  }
}
```

### 2.2 Global Settings

- `default_timeout` (integer, optional): Default subprocess timeout in seconds. Defaults to `60` if omitted. Applied to any command that does not specify its own `timeout`.

### 2.3 Command Definition Fields

- `command` (array of strings, required): The executable prefix. First element is the executable; remaining elements are fixed arguments. The array is passed directly to `subprocess.run` as the start of the argv list.
- `allow_extra_args` (boolean, required): When `true`, the MCP tool schema includes an `args` parameter and caller-provided args are appended to the `command` array. When `false`, the tool schema has no `args` parameter.
- `cwd` (string, required): Absolute path to the working directory for subprocess execution.
- `timeout` (integer, optional): Per-command timeout override in seconds. If omitted, `default_timeout` applies. Useful for long-running commands like test suites.

### 2.4 Validation at Startup

The allowlist file is parsed and validated using the `CommandsConfig` and `CommandEntry` pydantic models (see §6.1). The server exits with a non-zero exit code if pydantic validation fails — the error message includes field-level detail from pydantic's validation output.

On successful startup, the server logs:
- Number of commands loaded and their names.
- Effective timeout for each command (per-command override or global default).

---

## 3. Argument Validation

### 3.1 Metacharacter Blocklist

The following characters and sequences are rejected in any caller-provided argument string:

`;`, `&&`, `||`, `|`, `` ` ``, `$(`, `)` (when preceded by `$(`), `>`, `<`

Rejection is by substring match. If any argument contains a blocked sequence, the tool call returns `isError: true` before execution.

### 3.2 Type Validation

Each element in the `args` array must be a JSON string. The MCP tool schema declares `"items": {"type": "string"}`, so the SDK may enforce this at the protocol level. The `validate_args` function provides defense-in-depth for cases where schema validation is bypassed.

---

## 4. JSONL Log Format

### 4.1 Log File Location

Default path: `/bridge/logs/bridge.jsonl`

The directory is volume-mounted from the host. The server creates the file on first write if it does not exist.

### 4.2 Log Entry Schema

One JSON object per line, no trailing comma, newline-terminated. Each line is produced by `LogEntry.model_dump_json()` (see §6.1 for the pydantic model definition).

Successful execution:

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

Rejected — argument validation:

```json
{
  "timestamp": "2026-04-01T14:22:08.456Z",
  "command": "run_tests",
  "args": ["--flag; rm -rf /"],
  "exit_code": null,
  "duration_ms": 0,
  "stdout": null,
  "stderr": null,
  "stdout_bytes": 0,
  "stderr_bytes": 0,
  "rejected": true,
  "rejection_reason": "Argument contains disallowed characters: '--flag; rm -rf /'"
}
```

Rejected — busy (concurrent execution):

```json
{
  "timestamp": "2026-04-01T14:22:09.001Z",
  "command": "run_lint",
  "args": [],
  "exit_code": null,
  "duration_ms": 0,
  "stdout": null,
  "stderr": null,
  "stdout_bytes": 0,
  "stderr_bytes": 0,
  "rejected": true,
  "rejection_reason": "Bridge is busy executing 'run_tests'. Retry after it completes."
}
```

Full stdout/stderr content is included for audit trail and debugging. Future: payload logging may be made configurable (on/off via `BRIDGE_LOG_PAYLOADS` env var) to manage log volume.

### 4.3 Write Behavior

The log file is opened in append mode, one line is written, and the file is closed — per request. No file handle is held open between requests. This ensures entries are flushed immediately and the server does not leak file descriptors.

---

## 5. Server Configuration

All configuration is via environment variables with sensible defaults, loaded into a `BridgeConfig` pydantic model at startup (see §6.1). No config file for the server itself (the allowlist is for commands, not server settings).

| Variable | Default | Description |
|---|---|---|
| `BRIDGE_PORT` | `7357` | Port the MCP HTTP server listens on |
| `BRIDGE_HOST` | `0.0.0.0` | Bind address |
| `BRIDGE_COMMANDS_FILE` | `/bridge/commands.json` | Path to the allowlist config |
| `BRIDGE_LOG_DIR` | `/bridge/logs` | Directory for the JSONL log file |
| `BRIDGE_LOG_FILE` | `bridge.jsonl` | Log file name within the log directory |

Note: Timeout configuration lives in `commands.json` (§2.2 and §2.3), not in environment variables. This keeps timeout policy co-located with the command definitions that the operator controls.

---

## 6. server.py Module Structure

The server is a single file. Internal organization:

### 6.1 Pydantic Models

```python
class CommandEntry(BaseModel):
    """A single command in the allowlist."""
    command: list[str]              # Non-empty; first element is executable
    allow_extra_args: bool
    cwd: str
    timeout: int | None = None     # Per-command override; None = use default

    @field_validator("command")
    @classmethod
    def command_must_be_nonempty(cls, v):
        if not v:
            raise ValueError("command must be a non-empty list")
        return v


class CommandsConfig(BaseModel):
    """The entire commands.json file."""
    default_timeout: int = 60
    commands: dict[str, CommandEntry]

    def effective_timeout(self, name: str) -> int:
        """Return per-command timeout if set, otherwise default_timeout."""
        entry = self.commands[name]
        return entry.timeout if entry.timeout is not None else self.default_timeout


class CommandResult(BaseModel):
    """Subprocess execution result, serialized into MCP tool result text."""
    stdout: str
    stderr: str
    exit_code: int
    warnings: list[str] | None = None   # unsupported pipe flags; omitted when None
    cache_id: str | None = None          # present when cache=True was requested
    cache_age_ms: int | None = None      # present when cache_id was provided


class LogEntry(BaseModel):
    """Single JSONL log line. Serialized via model_dump_json()."""
    timestamp: datetime
    command: str | None
    args: list[str] | None
    exit_code: int | None
    duration_ms: int
    stdout: str | None              # Full content for audit
    stderr: str | None              # Full content for audit
    stdout_bytes: int
    stderr_bytes: int
    rejected: bool
    rejection_reason: str | None = None


class BridgeConfig(BaseModel):
    """Server configuration loaded from environment variables."""
    port: int = 7357
    host: str = "0.0.0.0"
    commands_file: str = "/bridge/commands.json"
    log_dir: str = "/bridge/logs"
    log_file: str = "bridge.jsonl"
```

`BridgeConfig` fields are populated from environment variables with the `BRIDGE_` prefix (e.g., `BRIDGE_PORT` → `port`). This is done via a factory function that reads `os.environ` with fallbacks to the model defaults — not via pydantic-settings (avoids an additional dependency).

### 6.2 Functions

```
server.py
│
├── Models (§6.1 above)
│
├── Concurrency guard
│   An asyncio.Lock held during command execution.
│   Tool handlers acquire non-blocking (trylock pattern).
│   If the lock is held, immediately return isError with
│   the name of the in-progress command and a retry message.
│   The currently executing command name is tracked in a
│   module-level variable set before acquire and cleared
│   after release.
│
├── load_config() → BridgeConfig
│   Read BRIDGE_* env vars, return validated config.
│
├── load_commands(path) → CommandsConfig
│   Read JSON file, validate via CommandsConfig model.
│   Raise SystemExit with pydantic error detail on failure.
│
├── validate_args(args) → None | str
│   Check args are strings without metacharacters.
│   Return None if valid, error message string if invalid.
│
├── execute_command(name, args, config: CommandsConfig) → CommandResult
│   Look up command, build argv, run subprocess with
│   config.effective_timeout(name). Return CommandResult.
│   Raise on timeout or exec failure.
│
├── log_request(entry: LogEntry, log_dir, log_file)
│   Append entry.model_dump_json() + newline to log file.
│
├── build_tools(config: CommandsConfig) → list[Tool]
│   Generate MCP Tool definitions from CommandsConfig.
│   Commands with allow_extra_args get args in schema;
│   others get empty schema.
│
├── Tool handler functions
│   One handler registered per tool name. Each handler:
│   0. Try to acquire concurrency lock (non-blocking).
│      If busy → log rejection, return isError with
│      retry message naming the in-progress command.
│   1. Extracts args from tool input (if schema allows)
│   2. Validates args
│   3. Calls execute_command → CommandResult
│   4. Constructs LogEntry (including full stdout/stderr),
│      calls log_request
│   5. Releases concurrency lock
│   6. Returns MCP tool result:
│      content=result.model_dump_json(), isError=False
│      or error message string, isError=True
│
└── main()
    load_config, load_commands, build_tools,
    create MCP Server instance, configure Streamable HTTP
    transport, start serving.
```

---

## 7. Dependencies

### 7.1 requirements.txt

```
mcp>=1.1.0
```

The `mcp` package pulls in its transitive dependencies including `pydantic`. The bridge code imports directly from both `mcp` and `pydantic` (see ADR 002). No additional packages beyond what the MCP SDK provides.

Pinned versions will be determined during implementation and locked in `requirements.txt`.

### 7.2 Python Version

Python 3.11 or higher (matching the MCP SDK's minimum requirement).

---

## 8. Consumer Integration Specifications

These specs define what a host project must provide to use the bridge. The bridge project itself does not contain these files.

### 8.1 Dockerfile Dev Stage

The host project's Dockerfile pulls the bridge from a named `FROM` stage and adds a `dev-with-bridge` stage that layers the bridge onto the host's existing dev image:

```dockerfile
FROM base AS dev
# Install dev dependencies (pytest, ruff, mypy, etc.)
RUN pip install -e ".[dev]"

# Pull the bridge from ghcr.io (pin to a specific tag for reproducible builds)
FROM ghcr.io/benjaminbradley/mcp-docker-cli-bridge:latest AS bridge

FROM dev AS dev-with-bridge
COPY --from=bridge /bridge/server.py /bridge/server.py
COPY --from=bridge /bridge/requirements.txt /bridge/requirements.txt
RUN pip install --no-cache-dir -r /bridge/requirements.txt
# Default: start bridge server
ENTRYPOINT ["python", "/bridge/server.py"]
```

The bridge image is fetched from the registry at build time — no local checkout of the bridge repo required. A local-checkout alternative (via Docker's `additional_contexts` feature) is available for developing against an unpublished version of the bridge; see the README's Step 3 for details.

### 8.2 Compose Dev Override (docker-compose.dev.yml)

```yaml
services:
  app:
    build:
      target: dev-with-bridge
    entrypoint: ["python", "/bridge/server.py"]
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

The `entrypoint:` on the service is required in addition to the `ENTRYPOINT` in the Dockerfile — if the base `docker-compose.yml` sets a different entrypoint for the app service, the Dockerfile's is silently ignored without this override.

### 8.3 MCP Registration (.mcp.json)

A file at the consumer project root that registers the bridge with Claude Code:

```json
{
  "mcpServers": {
    "dev-bridge": {
      "type": "http",
      "url": "http://<compose-service-name>:7357/mcp"
    }
  }
}
```

The `<compose-service-name>` is the Docker Compose service name as visible on the shared bridge network.

Alternatively, operators can register via CLI without committing to the repo:
```bash
claude mcp add --transport http dev-bridge http://<service>:7357/mcp --scope local
```

### 8.4 Makefile Dual-Mode Targets

The host project's Makefile detects whether the dev container is running and switches execution mode:

```makefile
# Detect running dev container
DEV_RUNNING := $(shell docker compose -f docker-compose.yml -f docker-compose.dev.yml ps -q app 2>/dev/null)

# If dev container is running, exec into it; otherwise, run ephemeral
ifdef DEV_RUNNING
  DOCKER_CMD = docker compose -f docker-compose.yml -f docker-compose.dev.yml exec app
else
  DOCKER_CMD = docker compose run --rm --entrypoint "" app
endif

test:
	$(DOCKER_CMD) python -m pytest src/tests/ -v
```

The bridge is not involved. This mode switch gives the human operator the same targets regardless of whether the dev environment is active.

### 8.5 Pre-commit Hook (scripts/pre-commit)

A shell script installed as `.git/hooks/pre-commit`. Uses `curl` for HTTP and `node` for JSON parsing (both available in the Claude Code container by default).

```bash
#!/usr/bin/env bash
set -euo pipefail

BRIDGE_URL="${BRIDGE_URL:-http://localhost:7357/mcp}"

call_bridge() {
  local tool_name="$1"
  local response
  response=$(curl -sf -X POST "$BRIDGE_URL" \
    -H "Content-Type: application/json" \
    -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"$tool_name\",\"arguments\":{}}}" 2>&1) || {
    echo "ERROR: Bridge unreachable at $BRIDGE_URL" >&2
    echo "Is the dev container running? Start it with: make dev-up" >&2
    exit 1
  }

  local exit_code
  exit_code=$(echo "$response" | node -e "
    const chunks = [];
    process.stdin.on('data', c => chunks.push(c));
    process.stdin.on('end', () => {
      const r = JSON.parse(chunks.join(''));
      const content = JSON.parse(r.result.content[0].text);
      process.stdout.write(String(content.exit_code));
    });
  ")

  if [ "$exit_code" -ne 0 ]; then
    echo "FAILED: $tool_name (exit code $exit_code)" >&2
    echo "$response" | node -e "
      const chunks = [];
      process.stdin.on('data', c => chunks.push(c));
      process.stdin.on('end', () => {
        const r = JSON.parse(chunks.join(''));
        const content = JSON.parse(r.result.content[0].text);
        if (content.stdout) process.stderr.write(content.stdout);
        if (content.stderr) process.stderr.write(content.stderr);
      });
    "
    exit 1
  fi
  echo "PASSED: $tool_name"
}

call_bridge "run_lint"
call_bridge "run_typecheck"
call_bridge "run_tests"
```

---

## 9. Consumer File Layout

Files the consumer project provides:

```
example-app/
├── commands.json              # Bridge allowlist (project-specific)
├── .mcp.json                  # MCP registration for Claude Code
├── docker-compose.dev.yml     # Dev overlay (bridge integration)
├── docker/
│   └── Dockerfile             # Multi-stage: base → dev
├── scripts/
│   └── pre-commit             # Bridge-based pre-commit hook
├── doc/
│   └── DEVELOPMENT.md         # Dev workflow guide (references bridge)
└── ...                        # (existing project files unchanged)
```

None of these files modify the application source code under `src/`. Removing the bridge integration means deleting `commands.json`, `.mcp.json`, `docker-compose.dev.yml`, the `dev` stage from the Dockerfile, and the pre-commit hook — then the project reverts to its original ephemeral-container workflow.
