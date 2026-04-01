# Implementation Plan — MCP Docker CLI Bridge

> **Status:** Active
> **Created:** 2026-04-01
> **References:** [Requirements](REQUIREMENTS.md) · [Architecture](ARCHITECTURE.md) · [Specs](SPECS.md) · [ADR 001](adr/001-mcp-transport.md) · [ADR 002](adr/002-pydantic-models.md)

Legend:

`[ ]` = Planned
`[~]` = In progress
`[o]` = Implemented
`[x]` = Verified
`[-]` = Skipped with reason

---

## Phase 0 — MCP Server Skeleton, Models, and Config Loader

**Goal:** A running MCP server that loads and validates `commands.json` on startup via pydantic models, registers tools from the whitelist, and responds to `tools/list`. No command execution yet — just startup, config validation, tool registration, and transport.

### 0.1 — Create requirements.txt
- [ ] Create `requirements.txt` at project root with `mcp>=1.1.0` and pydantic and any other dependencies imported directly by the app (don't rely on mcp to pull them in).
- [ ] **Verify:** `pip install -r requirements.txt` in a clean venv installs the MCP SDK and its transitive dependencies (including pydantic, starlette, uvicorn).

### 0.2 — Create server.py with pydantic models and config loader
- [ ] Create `server.py` at project root with: pydantic models (`BridgeConfig`, `CommandEntry`, `CommandsConfig`, `CommandResult`, `LogEntry`) per SPECS.md §6.1; `load_config()` factory reading `BRIDGE_*` env vars; `load_commands(path)` parsing JSON into `CommandsConfig`.
- [ ] `CommandsConfig` must support `default_timeout` at top level and optional per-command `timeout` overrides with `effective_timeout()` method per SPECS.md §6.1.
- [ ] `load_commands` must exit non-zero with pydantic's field-level error detail for: missing file, invalid JSON, missing required fields, wrong types, empty command array.
- [ ] Startup prints a banner: port, bind address, config file path, number of commands loaded with their names, effective timeout for each.
- [ ] **Verify:** Create a test `commands.json` per SPECS.md §2.1 (including one command with a timeout override and one without). Run `python server.py` directly. Confirm banner shows correct command names, counts, and effective timeouts. Test invalid configs: remove a required field → pydantic error with field name; set `command` to empty array → custom validator error; malform JSON → clear parse error.

### 0.3 — Tool registration and tools/list
- [ ] Implement `build_tools(config)` per SPECS.md §1.2: generate MCP tool definitions from `CommandsConfig`. Commands with `allow_extra_args: true` get `args` in schema; others get empty schema. Description is auto-generated from executable prefix.
- [ ] Create MCP Server instance, register tools, configure Streamable HTTP transport on `BRIDGE_HOST:BRIDGE_PORT`.
- [ ] **Verify:** Start the server. Use the MCP Inspector (`npx @modelcontextprotocol/inspector`) or curl to confirm `tools/list` returns the expected tool definitions matching the test `commands.json`. Confirm tools with `allow_extra_args: false` have no `args` in their schema.

---

## Phase 1 — Command Execution and Concurrency Guard

**Goal:** Tool calls resolve command names, validate arguments, run subprocesses with per-command timeouts, and return `CommandResult` as structured MCP tool results. Concurrent calls are rejected with a retry message. All error paths return proper MCP tool errors.

### 1.1 — Concurrency guard
- [ ] Implement an `asyncio.Lock`-based concurrency guard per SPECS.md §6.2 and REQUIREMENTS.md §4.6. Track the currently executing command name in a module-level variable. Tool handlers attempt non-blocking acquire; if the lock is held, immediately return `isError: true` with a message naming the in-progress command and telling the client to retry.
- [ ] **Verify:** Start the server with a command that sleeps for 5 seconds (e.g., `["sleep", "5"]`). Call the sleep tool, then immediately call another tool. Confirm the second call returns `isError: true` with a message like `"Bridge is busy executing 'sleep_cmd'. Retry after it completes."` Confirm the first call completes normally after the sleep.

### 1.2 — Argument validator
- [ ] Implement `validate_args(args)` per SPECS.md §3: type check (all strings), metacharacter blocklist scan. Returns `None` if valid, error message string if invalid.
- [ ] **Verify:** Call directly in a Python REPL. `validate_args(["--tb=short"])` → `None`. `validate_args(["--flag; rm -rf /"])` → error string. `validate_args([123])` → error string.

### 1.3 — Executor
- [ ] Implement `execute_command(name, args, config)` per SPECS.md §6.2: whitelist lookup, `subprocess.run` with `shell=False`, `capture_output=True`, `text=True`, `config.effective_timeout(name)`, `cwd`. Return `CommandResult` model.
- [ ] Raise appropriate exceptions for timeout and file-not-found.
- [ ] **Verify:** With a test `commands.json` containing an `echo` command (`["echo", "hello"]`, `allow_extra_args: true`, no per-command timeout), call `execute_command("echo", ["world"], config)` directly. Confirm returned `CommandResult` has `stdout="hello world\n"`, `exit_code=0`. Verify that a command with a 1-second timeout and a `sleep 5` target raises `TimeoutExpired`.

### 1.4 — Wire executor into tool handlers
- [ ] Implement tool handler functions that: acquire concurrency lock (reject if busy), extract `args` from tool input (if schema allows), call `validate_args`, call `execute_command`, release lock (via finally). Return MCP tool result per SPECS.md §1.3. Success result text is `CommandResult.model_dump_json()`.
- [ ] Non-zero subprocess exit codes → `isError: false` (faithful reporting).
- [ ] Argument validation failure → `isError: true`.
- [ ] Timeout → `isError: true` with timeout message including the effective timeout value.
- [ ] Exec failure (FileNotFoundError) → `isError: true`.
- [ ] **Verify (success path):** Start server with test `commands.json`. Use MCP Inspector to call the `echo` tool with `args: ["world"]`. Confirm result contains stdout/stderr/exit_code JSON.
- [ ] **Verify (error paths):** Call a tool with metacharacter args → `isError: true`. Misconfigure a command to reference a missing executable → `isError: true` on call.

---

## Phase 2 — Request Logging

**Goal:** Every tool invocation (successful, rejected, or busy) is logged to a JSONL file with full request/response payloads per SPECS.md §4.

### 2.1 — Implement log_request
- [ ] Implement `log_request(entry: LogEntry, log_dir, log_file)`: append `entry.model_dump_json()` + newline to log file. Create log directory if it does not exist.
- [ ] **Verify:** After a few tool calls via MCP Inspector, inspect the log file. Confirm each line is valid JSON with all expected fields matching `LogEntry` schema. Confirm full stdout/stderr content is present. Confirm rejected requests have `rejected: true`, a reason, and null stdout/stderr.

### 2.2 — Integrate logging into tool handlers
- [ ] Construct `LogEntry` at the end of every tool handler path (success, error, and busy rejection), including full stdout/stderr content from `CommandResult` where applicable. Capture wall-clock duration using `time.monotonic()` around the execution call.
- [ ] **Verify:** Send a successful tool call, a rejected tool call (bad args), and a busy rejection (concurrent call). Confirm all three produce log entries with correct `rejected` and `rejection_reason` values. Confirm `duration_ms` is non-zero for executed commands and zero for rejected/busy requests.

---

## Phase 3 — Integration Verification

**Goal:** Verify the bridge works end-to-end in its intended deployment context: inside a Docker container on a bridge network, with a consumer project's commands.json and Claude Code as the MCP client.

### 3.1 — Consumer integration files for example-app
- [ ] In the example-app project, create the integration files per SPECS.md §8 and §9: `commands.json` (with `default_timeout` and per-command overrides), `docker-compose.dev.yml`, Dockerfile `dev` stage, `.mcp.json`, `doc/DEVELOPMENT.md`.
- [ ] Add `dev-up` and `dev-down` targets to example-app Makefile.
- [ ] **Verify:** `make dev-up` builds the dev image (including bridge + MCP SDK), starts the container, and the bridge server starts listening with correct timeouts shown in banner. `make dev-down` stops it cleanly.

### 3.2 — MCP client verification
- [ ] With the dev container running, configure Claude Code to connect to the bridge (via `.mcp.json` or `claude mcp add`).
- [ ] **Verify:** Claude Code discovers the tools via `tools/list`. Running a tool call (e.g., `run_tests`) returns pytest output. Running `run_lint` returns ruff output. The bridge JSONL log on the host contains entries for each call with full payloads.

### 3.3 — Pre-commit hook
- [ ] Create pre-commit hook script in example-app per SPECS.md §8.5 (using node for JSON parsing).
- [ ] Document installation in `doc/DEVELOPMENT.md`.
- [ ] **Verify:** With the dev container running, `git commit` triggers lint/typecheck/test via the bridge. A failing check blocks the commit with clear output. Bridge unreachable → clear error message suggesting `make dev-up`.

### 3.4 — Makefile dual-mode
- [ ] Update example-app Makefile targets (`test`, `lint`, `typecheck`, `format`) to use the `DEV_RUNNING` detection pattern per SPECS.md §8.4.
- [ ] **Verify:** With dev container running, `make test` uses `exec`. With dev container stopped, `make test` uses `run --rm`. Both produce the same test results.

---

## Deferred

- **Configurable payload logging:** Add `BRIDGE_LOG_PAYLOADS` env var (default: true) to allow disabling stdout/stderr content in logs for high-throughput environments.
- **Structured stderr logging:** The server could emit structured JSON to stderr for container log aggregation.
