# Implementation Plan — Docker CLI Access Bridge MCP

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
- [ ] Create `requirements.txt` at project root with `mcp>=1.1.0`.
- [ ] **Verify:** `pip install -r requirements.txt` in a clean venv installs the MCP SDK and its transitive dependencies (including pydantic, starlette, uvicorn).

### 0.2 — Create server.py with pydantic models and config loader
- [ ] Create `server.py` at project root with: pydantic models (`BridgeConfig`, `CommandEntry`, `CommandsConfig`, `CommandResult`, `LogEntry`) per SPECS.md §6.1; `load_config()` factory reading `BRIDGE_*` env vars; `load_commands(path)` parsing JSON into `CommandsConfig`.
- [ ] `load_commands` must exit non-zero with pydantic's field-level error detail for: missing file, invalid JSON, missing required fields, wrong types, empty command array.
- [ ] Startup prints a banner: port, bind address, config file path, number of commands loaded with their names.
- [ ] **Verify:** Create a test `commands.json` with 2-3 entries (e.g., `echo`, `ls`). Run `python server.py` directly. Confirm banner prints with correct command names and count. Test invalid configs: remove a required field → pydantic error with field name; set `command` to empty array → custom validator error; malform JSON → clear parse error.

### 0.3 — Tool registration and tools/list
- [ ] Implement `build_tools(commands)` per SPECS.md §1.2: generate MCP tool definitions from `CommandsConfig`. Commands with `allow_extra_args: true` get `args` in schema; others get empty schema. Description is auto-generated from executable prefix.
- [ ] Create MCP Server instance, register tools, configure Streamable HTTP transport on `BRIDGE_HOST:BRIDGE_PORT`.
- [ ] **Verify:** Start the server. Use the MCP Inspector (`npx @modelcontextprotocol/inspector`) or curl to confirm `tools/list` returns the expected tool definitions matching the test `commands.json`. Confirm tools with `allow_extra_args: false` have no `args` in their schema.

---

## Phase 1 — Command Execution

**Goal:** Tool calls resolve command names, validate arguments, run subprocesses, and return `CommandResult` as structured MCP tool results. All error paths return proper MCP tool errors.

### 1.1 — Argument validator
- [ ] Implement `validate_args(args)` per SPECS.md §3: type check (all strings), metacharacter blocklist scan. Returns `None` if valid, error message string if invalid.
- [ ] **Verify:** Call directly in a Python REPL. `validate_args(["--tb=short"])` → `None`. `validate_args(["--flag; rm -rf /"])` → error string. `validate_args([123])` → error string.

### 1.2 — Executor
- [ ] Implement `execute_command(name, args, commands, timeout)` per SPECS.md §6.2: whitelist lookup, `subprocess.run` with `shell=False`, `capture_output=True`, `text=True`, `timeout`, `cwd`. Return `CommandResult` model.
- [ ] Raise appropriate exceptions for timeout and file-not-found.
- [ ] **Verify:** With a test `commands.json` containing an `echo` command (`["echo", "hello"]`, `allow_extra_args: true`), call `execute_command("echo", ["world"], commands, 60)` directly. Confirm returned `CommandResult` has `stdout="hello world\n"`, `exit_code=0`.

### 1.3 — Wire executor into tool handlers
- [ ] Implement tool handler functions that: extract `args` from tool input (if schema allows), call `validate_args`, call `execute_command`, return MCP tool result per SPECS.md §1.3. Success result text is `CommandResult.model_dump_json()`.
- [ ] Non-zero subprocess exit codes → `isError: false` (faithful reporting).
- [ ] Argument validation failure → `isError: true`.
- [ ] Timeout → `isError: true` with timeout message.
- [ ] Exec failure (FileNotFoundError) → `isError: true`.
- [ ] **Verify (success path):** Start server with test `commands.json`. Use MCP Inspector to call the `echo` tool with `args: ["world"]`. Confirm result contains stdout/stderr/exit_code JSON.
- [ ] **Verify (error paths):** Call a tool with metacharacter args → `isError: true`. Misconfigure a command to reference a missing executable → `isError: true` on call.

---

## Phase 2 — Request Logging

**Goal:** Every tool invocation (successful or rejected) is logged to a JSONL file with metadata per SPECS.md §4.

### 2.1 — Implement log_request
- [ ] Implement `log_request(entry: LogEntry, log_dir, log_file)`: append `entry.model_dump_json()` + newline to log file. Create log directory if it does not exist.
- [ ] **Verify:** After a few tool calls via MCP Inspector, inspect the log file. Confirm each line is valid JSON with all expected fields matching `LogEntry` schema. Confirm rejected requests have `rejected: true` and a reason. Confirm stdout/stderr content is NOT in the log (only byte lengths).

### 2.2 — Integrate logging into tool handlers
- [ ] Construct `LogEntry` at the end of every tool handler path (both success and error). Capture wall-clock duration using `time.monotonic()` around the execution call.
- [ ] **Verify:** Send a successful tool call and a rejected tool call. Confirm both produce log entries. Confirm `duration_ms` is non-zero for executed commands and zero for rejected requests.

---

## Phase 3 — Integration Verification

**Goal:** Verify the bridge works end-to-end in its intended deployment context: inside a Docker container on a bridge network, with a consumer project's commands.json and Claude Code as the MCP client.

### 3.1 — Consumer integration files for example-app
- [ ] In example-app, create the integration files per SPECS.md §8 and §9: `commands.json`, `docker-compose.dev.yml`, Dockerfile `dev` stage, `.mcp.json`, `doc/DEVELOPMENT.md`.
- [ ] Add `dev-up` and `dev-down` targets to example-app Makefile.
- [ ] **Verify:** `make dev-up` builds the dev image (including bridge + MCP SDK), starts the container, and the bridge server starts listening. `make dev-down` stops it cleanly.

### 3.2 — MCP client verification
- [ ] With the dev container running, configure Claude Code to connect to the bridge (via `.mcp.json` or `claude mcp add`).
- [ ] **Verify:** Claude Code discovers the tools via `tools/list`. Running a tool call (e.g., `run_tests`) returns pytest output. Running `run_lint` returns ruff output. The bridge JSONL log on the host contains entries for each call.

### 3.3 — Pre-commit hook
- [ ] Create pre-commit hook script in example-app per SPECS.md §8.5.
- [ ] Document installation in `doc/DEVELOPMENT.md`.
- [ ] **Verify:** With the dev container running, `git commit` triggers lint/typecheck/test via the bridge. A failing check blocks the commit with clear output. Bridge unreachable → clear error message suggesting `make dev-up`.

### 3.4 — Makefile dual-mode
- [ ] Update example-app Makefile targets (`test`, `lint`, `typecheck`, `format`) to use the `DEV_RUNNING` detection pattern per SPECS.md §8.4.
- [ ] **Verify:** With dev container running, `make test` uses `exec`. With dev container stopped, `make test` uses `run --rm`. Both produce the same test results.

---

## Deferred

- **Bridge test suite:** Unit tests for server.py (arg validation, config loading, executor, tool schema generation, pydantic model validation). Not blocking MVP — the bridge is verified through MCP Inspector testing and through the consumer project's test suite running over it. Tracked for future hardening.
- **Structured stderr logging:** The server could emit structured JSON to stderr for container log aggregation.
- **Concurrent tool execution:** The MCP SDK supports async, but tool execution is serialized. If concurrent execution becomes needed, the executor could use `asyncio.to_thread`.
