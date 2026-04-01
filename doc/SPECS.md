# Specifications — Docker CLI Access Bridge

> **Status:** Approved
> **Last updated:** 2026-03-31
> **References:** [Requirements](REQUIREMENTS.md) · [Architecture](ARCHITECTURE.md)

---

## 1. Server API

### 1.1 Endpoint

```
POST /execute
Content-Type: application/json
```

All other paths return HTTP 404 with `{"error": "Not found"}`. All methods other than POST return HTTP 405 with `{"error": "Method not allowed"}`.

### 1.2 Request Schema

```json
{
  "command": "run_tests",
  "args": ["--tb=short", "-x"]
}
```

- `command` (string, required): Name matching a key in the command whitelist.
- `args` (array of strings, optional): Additional arguments appended to the command's executable prefix. Defaults to `[]` if omitted.

### 1.3 Success Response

HTTP 200:

```json
{
  "stdout": "===== 68 passed in 2.31s =====\n",
  "stderr": "",
  "exit_code": 0
}
```

- `stdout` (string): Captured standard output.
- `stderr` (string): Captured standard error.
- `exit_code` (integer): Process return code.

A non-zero `exit_code` is still HTTP 200 — the bridge faithfully reports what the subprocess returned. HTTP status codes reflect bridge-level errors, not subprocess outcomes.

### 1.4 Error Responses

All error responses include an `error` field with a human-readable message. Fields that don't apply are omitted (not set to null).

**Unknown command** — HTTP 400:
```json
{
  "error": "Unknown command: 'deploy'",
  "available_commands": ["run_tests", "run_lint", "run_typecheck"]
}
```

**Extra args not allowed** — HTTP 400:
```json
{
  "error": "Command 'run_lint' does not allow extra arguments"
}
```

**Argument validation failure** — HTTP 400:
```json
{
  "error": "Argument contains disallowed characters: '--flag; rm -rf /'"
}
```

**Malformed JSON** — HTTP 400:
```json
{
  "error": "Invalid JSON in request body"
}
```

**Missing command field** — HTTP 400:
```json
{
  "error": "Missing required field: 'command'"
}
```

**Command timeout** — HTTP 504:
```json
{
  "error": "Command 'run_tests' timed out after 60s",
  "stdout": "(partial output if captured)",
  "stderr": "(partial output if captured)"
}
```

**Subprocess failure** (e.g., executable not found) — HTTP 500:
```json
{
  "error": "Failed to execute command 'run_tests': [Errno 2] No such file or directory: 'pythonn'"
}
```

---

## 2. Command Whitelist Schema (commands.json)

### 2.1 File Format

A JSON object where each key is a command name and each value is a command definition object.

```json
{
  "run_tests": {
    "command": ["python", "-m", "pytest", "src/tests/", "-v"],
    "allow_extra_args": true,
    "cwd": "/app"
  },
  "run_lint": {
    "command": ["python", "-m", "ruff", "check", "src/"],
    "allow_extra_args": false,
    "cwd": "/app"
  },
  "run_typecheck": {
    "command": ["python", "-m", "mypy", "src/findworkbot/"],
    "allow_extra_args": false,
    "cwd": "/app"
  },
  "run_format": {
    "command": ["python", "-m", "ruff", "format", "src/"],
    "allow_extra_args": false,
    "cwd": "/app"
  }
}
```

### 2.2 Command Definition Fields

- `command` (array of strings, required): The executable prefix. First element is the executable; remaining elements are fixed arguments. The array is passed directly to `subprocess.run` as the start of the argv list.
- `allow_extra_args` (boolean, required): When `true`, caller-provided `args` are appended to the `command` array. When `false`, any `args` in the request trigger an error.
- `cwd` (string, required): Absolute path to the working directory for subprocess execution.

### 2.3 Validation at Startup

The server validates the whitelist on startup and exits with a non-zero exit code if:
- The file is not valid JSON.
- The top-level value is not an object.
- Any command definition is missing a required field.
- `command` is not a non-empty array of strings.
- `allow_extra_args` is not a boolean.
- `cwd` is not a string.

The server logs the number of commands loaded on successful startup.

---

## 3. Argument Validation

### 3.1 Metacharacter Blocklist

The following characters and sequences are rejected in any caller-provided argument string:

`;`, `&&`, `||`, `|`, `` ` ``, `$(`, `)` (when preceded by `$(`), `>`, `<`

Rejection is by substring match. If any argument contains a blocked sequence, the entire request is rejected with HTTP 400 before execution.

### 3.2 Type Validation

Each element in the `args` array must be a JSON string. Non-string types (numbers, booleans, objects, arrays, null) are rejected with HTTP 400.

---

## 4. JSONL Log Format

### 4.1 Log File Location

Default path: `/bridge/logs/bridge.jsonl`

The directory is volume-mounted from the host. The server creates the file on first write if it does not exist.

### 4.2 Log Entry Schema

One JSON object per line, no trailing comma, newline-terminated.

```json
{
  "timestamp": "2026-03-31T14:22:05.123Z",
  "command": "run_tests",
  "args": ["--tb=short"],
  "exit_code": 0,
  "duration_ms": 2310,
  "stdout_bytes": 1847,
  "stderr_bytes": 0,
  "rejected": false,
  "rejection_reason": null
}
```

Rejected request example:

```json
{
  "timestamp": "2026-03-31T14:22:08.456Z",
  "command": "unknown_cmd",
  "args": [],
  "exit_code": null,
  "duration_ms": 0,
  "stdout_bytes": 0,
  "stderr_bytes": 0,
  "rejected": true,
  "rejection_reason": "Unknown command: 'unknown_cmd'"
}
```

Malformed request (command field unparseable):

```json
{
  "timestamp": "2026-03-31T14:22:10.789Z",
  "command": null,
  "args": null,
  "exit_code": null,
  "duration_ms": 0,
  "stdout_bytes": 0,
  "stderr_bytes": 0,
  "rejected": true,
  "rejection_reason": "Invalid JSON in request body"
}
```

### 4.3 Write Behavior

The log file is opened in append mode, one line is written, and the file is closed — per request. No file handle is held open between requests. This ensures entries are flushed immediately and the server does not leak file descriptors.

---

## 5. Server Configuration

All configuration is via environment variables with sensible defaults. No config file for the server itself (the whitelist is for commands, not server settings).

| Variable | Default | Description |
|---|---|---|
| `BRIDGE_PORT` | `7357` | Port the HTTP server listens on |
| `BRIDGE_HOST` | `0.0.0.0` | Bind address |
| `BRIDGE_COMMANDS_FILE` | `/bridge/commands.json` | Path to the whitelist config |
| `BRIDGE_LOG_DIR` | `/bridge/logs` | Directory for the JSONL log file |
| `BRIDGE_LOG_FILE` | `bridge.jsonl` | Log file name within the log directory |
| `BRIDGE_TIMEOUT` | `60` | Default subprocess timeout in seconds |

---

## 6. server.py Module Structure

The server is a single file. No classes except the HTTP handler subclass. Internal organization by function:

```
server.py
│
├── Constants / env var loading
│   BRIDGE_PORT, BRIDGE_HOST, COMMANDS_FILE, LOG_DIR, LOG_FILE, TIMEOUT
│
├── load_commands(path) → dict
│   Read and validate commands.json. Return command lookup dict.
│   Raise SystemExit on validation failure.
│
├── validate_args(args) → None | str
│   Check args are strings without metacharacters.
│   Return None if valid, error message string if invalid.
│
├── execute_command(name, args, commands) → (int, dict)
│   Look up command, build argv, run subprocess, return (http_status, response_dict).
│   Handles timeout, file-not-found, and unknown command cases.
│
├── log_request(entry, log_dir, log_file)
│   Append a single JSONL line to the log file.
│
├── class BridgeHandler(BaseHTTPRequestHandler)
│   do_POST(): route /execute, parse JSON, call execute_command, log, respond.
│   do_GET() / other: return 404/405.
│   log_message(): override to suppress default stderr logging.
│
└── main()
    Load commands, print startup banner, start HTTPServer, serve_forever.
```

---

## 7. Consumer Integration Specifications

These specs define what a host project (e.g., find-work-bot) must provide to use the bridge. The bridge project itself does not contain these files.

### 7.1 Dockerfile Dev Stage

The host project's Dockerfile adds a `dev` stage that extends the production image:

```dockerfile
FROM base AS dev
# Install dev dependencies (pytest, ruff, mypy, etc.)
RUN pip install -e ".[dev]"
# Copy bridge server from build context
COPY bridge/server.py /bridge/server.py
# Default: start bridge server
CMD ["python", "/bridge/server.py"]
```

The bridge file is included in the Docker build context via the compose override's `build.context` or `build.additional_contexts` configuration. The exact mechanism depends on the host project's compose version and directory layout.

### 7.2 Compose Dev Override (docker-compose.dev.yml)

```yaml
services:
  app:
    build:
      target: dev
      additional_contexts:
        bridge: ../docker-cli-access-bridge
    volumes:
      - ./src:/app/src                                    # Source code (rw)
      - ./commands.json:/bridge/commands.json:ro           # Whitelist (ro)
      - ./data/bridge-logs:/bridge/logs                    # Audit log (rw)
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

Key properties: the whitelist is mounted read-only, the bridge server is the container entrypoint (keeping it alive), and port 7357 is exposed on the network but not published to the host.

### 7.3 Makefile Dual-Mode Targets

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

### 7.4 Pre-commit Hook (scripts/pre-commit)

A shell script installed as `.git/hooks/pre-commit`:

```sh
#!/usr/bin/env bash
set -euo pipefail

BRIDGE_URL="${BRIDGE_URL:-http://localhost:7357}"

call_bridge() {
  local cmd="$1"
  local response
  response=$(curl -sf -X POST "$BRIDGE_URL/execute" \
    -H "Content-Type: application/json" \
    -d "{\"command\": \"$cmd\"}" 2>&1) || {
    echo "ERROR: Bridge unreachable at $BRIDGE_URL"
    echo "Start the dev container: make dev-up"
    exit 1
  }
  local exit_code
  exit_code=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin)['exit_code'])")
  if [ "$exit_code" -ne 0 ]; then
    echo "FAILED: $cmd (exit code $exit_code)"
    echo "$response" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('stdout','')); print(d.get('stderr',''))"
    exit 1
  fi
  echo "PASSED: $cmd"
}

call_bridge "run_lint"
call_bridge "run_typecheck"
call_bridge "run_tests"
```

The `BRIDGE_URL` defaults to `localhost:7357`, which works when the host publishes the port for debugging. In the standard setup (no host port), the pre-commit hook runs inside the Controller container where `http://<service-name>:7357` is used instead.

---

## 8. Consumer File Layout

Files the consumer project provides (using find-work-bot as the example):

```
find-work-bot/
├── commands.json              # Bridge whitelist (project-specific)
├── docker-compose.dev.yml     # Dev overlay (bridge integration)
├── docker/
│   └── Dockerfile             # Multi-stage: base → dev
├── scripts/
│   └── pre-commit             # Bridge-based pre-commit hook
├── doc/
│   └── DEVELOPMENT.md         # Dev workflow guide (references bridge)
├── CLAUDE.md                  # Updated with bridge API docs for CC
└── ...                        # (existing project files unchanged)
```

None of these files modify the application source code under `src/`. Removing the bridge integration means deleting `commands.json`, `docker-compose.dev.yml`, the `dev` stage from the Dockerfile, and the pre-commit hook — then the project reverts to its original ephemeral-container workflow.
