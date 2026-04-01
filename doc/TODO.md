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

## Test Structure

- **Test file:** `tests/test_server.py`
- **Run command:** `pytest tests/ -v`
- **Key test classes** (mirroring server components):
  - `TestCommandsConfig` — pydantic model validation for `CommandEntry` and `CommandsConfig`
  - `TestBuildTools` — tool schema generation from `CommandsConfig`
  - `TestValidateArgs` — argument type and metacharacter validation
  - `TestExecuteCommand` — subprocess execution, timeout, and exec failure
  - `TestToolHandlers` — integration-style tests through MCP tool handler functions
  - `TestLogRequest` — log file creation, JSONL format, all logged paths

---

## Phase 0 — MCP Server Skeleton, Models, and Config Loader

**Goal:** A running MCP server that loads and validates `commands.json` on startup via pydantic models, registers tools from the whitelist, and responds to `tools/list`. No command execution yet — just startup, config validation, tool registration, and transport.

### 0.0 — Dev container setup

> **Infrastructure task — no TDD cycle.** Creates the container environment in which all subsequent TDD cycles run.
> **Note:** `make build` requires 0.1's `requirements.txt` to exist first. Create 0.0 and 0.1 files together, then verify both.

- [o] Create `Dockerfile` (base stage: MCP SDK deps + server.py + non-root user; dev stage: adds pytest, ruff, mypy, pytest-asyncio)
- [o] Create `docker-compose.yml` (service `my-app`, port `127.0.0.1:7357:7357`, volumes: `commands.dev.json:ro`, `data/bridge-logs`, `server.py`, `tests/`)
- [o] Create `commands.dev.json` (e2e test whitelist: `echo_test`, `run_tests`, `run_lint`, `run_typecheck`, `run_format_check`, `sleep_test`)
- [o] Create `Makefile` (`help`, `build`, `up`, `down`, `logs`, `test`, `lint`, `typecheck`, `format`, `shell`)
- [o] Create `.mcp.json` (registers `http://my-app:7357/mcp` as `bridge-dev` MCP server)
- [-] **Verify:** Deferred to end of 0.2 — `make build` requires `requirements.txt` and `server.py`.
- **Files:** `Dockerfile`, `docker-compose.yml`, `commands.dev.json`, `Makefile`, `.mcp.json`

### 0.1 — Create requirements.txt

> **Infrastructure task — no TDD cycle.** This task installs dependencies with no testable logic. Verification is manual (`pip install`).

- [o] Create `requirements.txt` at project root with `mcp>=1.1.0` and pydantic and any other dependencies imported directly by the app (don't rely on mcp to pull them in).
- [-] **Verify:** Deferred to 0.2 combined verify (requires `make build`).
- **Files:** `requirements.txt`

### 0.2 — Create server.py with pydantic models and config loader

- [o] **RED:** In `tests/test_server.py`, add class `TestCommandsConfig`. Write tests covering:
  - `test_valid_config_parses_correctly` — a fully-populated `CommandsConfig` dict round-trips through the model with correct field values.
  - `test_missing_required_field_raises` — omitting `command` from a `CommandEntry` raises `ValidationError`.
  - `test_wrong_type_for_command_raises` — setting `command` to a string (not list) raises `ValidationError`.
  - `test_empty_command_array_raises` — setting `command` to `[]` raises `ValidationError` with message matching "non-empty".
  - `test_effective_timeout_uses_per_command_override` — a command with `timeout=30` and `default_timeout=60` returns `30` from `effective_timeout()`.
  - `test_effective_timeout_falls_back_to_default` — a command with `timeout=None` and `default_timeout=60` returns `60` from `effective_timeout()`.
  - `test_default_timeout_defaults_to_60` — `CommandsConfig` with no `default_timeout` field has `default_timeout == 60`.
  Run `pytest tests/ -v`, confirm all new tests fail with `ImportError` or `ModuleNotFoundError` (right reason: `server.py` does not exist yet).
- [o] **GREEN:** Create `server.py` with: pydantic models (`BridgeConfig`, `CommandEntry`, `CommandsConfig`, `CommandResult`, `LogEntry`) per SPECS.md §6.1; `load_config()` factory reading `BRIDGE_*` env vars; `load_commands(path)` parsing JSON into `CommandsConfig`. Run `pytest tests/ -v`, confirm all `TestCommandsConfig` tests pass.
- [-] **REFACTOR:** No refactoring needed — models are clean as written.
- [ ] **Verify (0.0 + 0.2 combined):**
  - `make build` succeeds.
  - `make up` starts the server; `make logs` shows the startup banner.
  - `make down` stops cleanly.
  - `make test` runs the full test suite and passes.
  - Claude Code discovers `bridge-dev` tools via `tools/list` (requires `make up`).
  - Invalid config edge cases: remove a required field → pydantic error with field name; set `command` to empty array → custom validator error; malform JSON → clear parse error.
- **Files:** `server.py` (create), `tests/test_server.py` (create)

### 0.3 — Tool registration and tools/list

- [ ] **RED:** In `tests/test_server.py`, add class `TestBuildTools`. Write tests covering:
  - `test_builds_one_tool_per_command` — `build_tools(config)` returns a list with the same number of tools as commands in `config`.
  - `test_tool_name_matches_command_name` — each tool's `name` matches its key in `commands`.
  - `test_allow_extra_args_true_includes_args_in_schema` — a command with `allow_extra_args=True` produces a tool whose `inputSchema.properties` contains an `args` key with `type: array, items: {type: string}`.
  - `test_allow_extra_args_false_has_empty_schema` — a command with `allow_extra_args=False` produces a tool whose `inputSchema.properties` is empty (`{}`).
  - `test_description_format` — tool description is `"Execute: "` followed by the command array joined by spaces.
  Run `pytest tests/ -v`, confirm new tests fail because `build_tools` does not exist yet (right reason: `AttributeError` or `ImportError`).
- [ ] **GREEN:** Implement `build_tools(config)` per SPECS.md §1.2: generate MCP tool definitions from `CommandsConfig`. Create MCP Server instance, register tools, configure Streamable HTTP transport on `BRIDGE_HOST:BRIDGE_PORT`. Run `pytest tests/ -v`, confirm all `TestBuildTools` tests pass.
- [ ] **REFACTOR:** Extract schema-building helpers if the function is long. Keep tests green.
- [ ] **Verify:** Start the server. Use the MCP Inspector (`npx @modelcontextprotocol/inspector`) or curl to confirm `tools/list` returns the expected tool definitions matching the test `commands.json`. Confirm tools with `allow_extra_args: false` have no `args` in their schema.
- **Files:** `server.py` (modify), `tests/test_server.py` (modify)

---

## Phase 1 — Command Execution and Concurrency Guard

**Goal:** Tool calls resolve command names, validate arguments, run subprocesses with per-command timeouts, and return `CommandResult` as structured MCP tool results. Concurrent calls are rejected with a retry message. All error paths return proper MCP tool errors.

### 1.1 — Concurrency guard

- [ ] **RED:** In `tests/test_server.py`, add class `TestConcurrencyGuard`. Write tests covering:
  - `test_second_call_rejected_while_first_running` — use `pytest-asyncio`; acquire the module-level lock directly in the test, then call the tool handler, confirm it returns `isError: true` with a message containing the in-progress command name and "Retry".
  - `test_lock_released_after_execution` — after a simulated execution completes (lock released), a subsequent call acquires the lock and succeeds.
  Run `pytest tests/ -v`, confirm new tests fail because the concurrency guard and handler scaffolding do not exist yet.
- [ ] **GREEN:** Implement an `asyncio.Lock`-based concurrency guard per SPECS.md §6.2 and REQUIREMENTS.md §4.6. Track the currently executing command name in a module-level variable. Tool handlers attempt non-blocking acquire; if the lock is held, immediately return `isError: true` with a message naming the in-progress command and telling the client to retry. Run `pytest tests/ -v`, confirm new tests pass.
- [ ] **REFACTOR:** Ensure lock acquisition and release follow a `try/finally` pattern. Keep tests green.
- [ ] **Verify:** Start the server with a command that sleeps for 5 seconds (e.g., `["sleep", "5"]`). Call the sleep tool, then immediately call another tool. Confirm the second call returns `isError: true` with a message like `"Bridge is busy executing 'sleep_cmd'. Retry after it completes."` Confirm the first call completes normally after the sleep.
- **Files:** `server.py` (modify), `tests/test_server.py` (modify)

### 1.2 — Argument validator

- [ ] **RED:** In `tests/test_server.py`, add class `TestValidateArgs`. Write tests covering:
  - `test_valid_args_returns_none` — `validate_args(["--tb=short"])` returns `None`.
  - `test_empty_args_returns_none` — `validate_args([])` returns `None`.
  - `test_semicolon_rejected` — `validate_args(["--flag; rm -rf /"])` returns a non-None error string.
  - `test_pipe_rejected` — `validate_args(["foo | bar"])` returns a non-None error string.
  - `test_double_ampersand_rejected` — `validate_args(["foo && bar"])` returns a non-None error string.
  - `test_double_pipe_rejected` — `validate_args(["foo || bar"])` returns a non-None error string.
  - `test_backtick_rejected` — args containing a backtick return a non-None error string.
  - `test_subshell_rejected` — `validate_args(["$(cmd)"])` returns a non-None error string.
  - `test_redirect_gt_rejected` — `validate_args(["> /etc/passwd"])` returns a non-None error string.
  - `test_redirect_lt_rejected` — `validate_args(["< /etc/shadow"])` returns a non-None error string.
  - `test_non_string_arg_rejected` — `validate_args([123])` returns a non-None error string.
  Run `pytest tests/ -v`, confirm new tests fail because `validate_args` does not exist yet.
- [ ] **GREEN:** Implement `validate_args(args)` per SPECS.md §3: type check (all strings), metacharacter blocklist scan. Returns `None` if valid, error message string if invalid. Run `pytest tests/ -v`, confirm all `TestValidateArgs` tests pass.
- [ ] **REFACTOR:** Extract the blocklist as a named constant. Keep tests green.
- [ ] **Verify:** Call directly in a Python REPL. `validate_args(["--tb=short"])` → `None`. `validate_args(["--flag; rm -rf /"])` → error string. `validate_args([123])` → error string.
- **Files:** `server.py` (modify), `tests/test_server.py` (modify)

### 1.3 — Executor

- [ ] **RED:** In `tests/test_server.py`, add class `TestExecuteCommand`. Write tests covering:
  - `test_captures_stdout_and_exit_code` — build a `CommandsConfig` with `["echo", "hello"]`, `allow_extra_args=True`; call `execute_command("echo", ["world"], config)`, confirm `CommandResult` has `stdout` containing `"hello world"` and `exit_code == 0`.
  - `test_captures_stderr` — use a command that writes to stderr; confirm `CommandResult.stderr` is non-empty.
  - `test_nonzero_exit_code_returned` — use `["python", "-c", "import sys; sys.exit(1)"]`; confirm `exit_code == 1` and no exception raised.
  - `test_timeout_raises` — build a config with `timeout=1`; use `["sleep", "5"]`; confirm `subprocess.TimeoutExpired` is raised.
  - `test_missing_executable_raises` — use `["nonexistent_binary_xyz"]`; confirm `FileNotFoundError` is raised.
  Run `pytest tests/ -v`, confirm new tests fail because `execute_command` does not exist yet.
- [ ] **GREEN:** Implement `execute_command(name, args, config: CommandsConfig)` per SPECS.md §6.2: whitelist lookup, `subprocess.run` with `shell=False`, `capture_output=True`, `text=True`, `config.effective_timeout(name)`, `cwd`. Return `CommandResult` model. Raise appropriate exceptions for timeout and file-not-found. Run `pytest tests/ -v`, confirm all `TestExecuteCommand` tests pass.
- [ ] **REFACTOR:** Ensure exception handling is clean and the function stays focused. Keep tests green.
- [ ] **Verify:** With a test `commands.json` containing an `echo` command (`["echo", "hello"]`, `allow_extra_args: true`, no per-command timeout), call `execute_command("echo", ["world"], config)` directly. Confirm returned `CommandResult` has `stdout="hello world\n"`, `exit_code=0`. Verify that a command with a 1-second timeout and a `sleep 5` target raises `TimeoutExpired`.
- **Files:** `server.py` (modify), `tests/test_server.py` (modify)

### 1.4 — Wire executor into tool handlers

- [ ] **RED:** In `tests/test_server.py`, add class `TestToolHandlers`. Write integration-style tests that call the registered MCP tool handler functions directly (bypassing HTTP transport). Tests should cover:
  - `test_success_path_returns_command_result_json` — call an echo-style tool handler; confirm result `content[0].text` is valid JSON containing `stdout`, `stderr`, `exit_code`; confirm `isError == False`.
  - `test_nonzero_exit_code_is_not_error` — call a tool that exits 1; confirm `isError == False` (faithful reporting).
  - `test_metacharacter_args_return_is_error` — call a tool handler with args containing `;`; confirm `isError == True`.
  - `test_timeout_returns_is_error` — configure a 1-second timeout command, pass it a slow execution; confirm `isError == True` and message contains the timeout value.
  - `test_exec_failure_returns_is_error` — configure a command pointing to a non-existent binary; confirm `isError == True`.
  - `test_busy_rejection_returns_is_error` — hold the concurrency lock externally; call a handler; confirm `isError == True` and message names the in-progress command.
  Run `pytest tests/ -v`, confirm new tests fail because tool handler wiring does not exist yet.
- [ ] **GREEN:** Implement tool handler functions that: acquire concurrency lock (reject if busy), extract `args` from tool input (if schema allows), call `validate_args`, call `execute_command`, release lock (via finally). Return MCP tool result per SPECS.md §1.3. Non-zero subprocess exit codes → `isError: false`. Argument validation failure → `isError: true`. Timeout → `isError: true` with timeout message including the effective timeout value. Exec failure (FileNotFoundError) → `isError: true`. Run `pytest tests/ -v`, confirm all `TestToolHandlers` tests pass.
- [ ] **REFACTOR:** Extract common error-response construction if repetitive. Keep tests green.
- [ ] **Verify (success path):** Start server with test `commands.json`. Use MCP Inspector to call the `echo` tool with `args: ["world"]`. Confirm result contains stdout/stderr/exit_code JSON.
- [ ] **Verify (error paths):** Call a tool with metacharacter args → `isError: true`. Misconfigure a command to reference a missing executable → `isError: true` on call.
- **Files:** `server.py` (modify), `tests/test_server.py` (modify)

---

## Phase 2 — Request Logging

**Goal:** Every tool invocation (successful, rejected, or busy) is logged to a JSONL file with full request/response payloads per SPECS.md §4.

### 2.1 — Implement log_request

- [ ] **RED:** In `tests/test_server.py`, add class `TestLogRequest`. Write tests covering:
  - `test_creates_log_file_if_not_exists` — call `log_request` with a `tmp_path`-based log dir; confirm the file is created with one line.
  - `test_creates_log_directory_if_not_exists` — call `log_request` with a nested subdirectory that does not exist; confirm the directory and file are created.
  - `test_appends_valid_jsonl_line` — call `log_request` twice; confirm the file has two lines, each valid JSON.
  - `test_log_entry_fields_present` — parse a written line; confirm all expected keys are present (`timestamp`, `command`, `args`, `exit_code`, `duration_ms`, `stdout`, `stderr`, `stdout_bytes`, `stderr_bytes`, `rejected`, `rejection_reason`).
  Run `pytest tests/ -v`, confirm new tests fail because `log_request` does not exist yet.
- [ ] **GREEN:** Implement `log_request(entry: LogEntry, log_dir, log_file)`: append `entry.model_dump_json()` + newline to log file. Create log directory if it does not exist. Open and close file per write. Run `pytest tests/ -v`, confirm all `TestLogRequest` tests pass.
- [ ] **REFACTOR:** Ensure file is opened and closed per-write (no held handle). Keep tests green.
- [ ] **Verify:** After a few tool calls via MCP Inspector, inspect the log file. Confirm each line is valid JSON with all expected fields. Confirm rejected requests have `rejected: true`, a reason, and null stdout/stderr.
- **Files:** `server.py` (modify), `tests/test_server.py` (modify)

### 2.2 — Integrate logging into tool handlers

- [ ] **RED:** Extend `TestToolHandlers` or add `TestLogIntegration`. Write tests covering:
  - `test_successful_call_logged` — after a successful handler call (with tmp-path log dir injected), confirm one log line with `rejected == False` and matching `exit_code`.
  - `test_rejected_call_logged_with_reason` — after a validation-rejected call, confirm one log line with `rejected == True`, non-null `rejection_reason`, and null `stdout`/`stderr`.
  - `test_busy_rejection_logged` — after a busy-rejection call, confirm log line with `rejected == True` and reason naming the in-progress command.
  - `test_duration_ms_nonzero_for_executed_commands` — confirm `duration_ms > 0` for a completed execution log entry.
  - `test_duration_ms_zero_for_rejected_requests` — confirm `duration_ms == 0` for validation-rejected and busy-rejected entries.
  Run `pytest tests/ -v`, confirm new tests fail because `log_request` is not yet wired into handlers.
- [ ] **GREEN:** Construct `LogEntry` at the end of every tool handler path (success, error, and busy rejection). Capture wall-clock duration using `time.monotonic()` around the execution call. Run `pytest tests/ -v`, confirm all logging integration tests pass.
- [ ] **REFACTOR:** Ensure all handler paths (success, validation error, timeout, exec failure, busy) construct and write a `LogEntry`. Keep tests green.
- [ ] **Verify:** Send a successful tool call, a rejected tool call (bad args), and a busy rejection (concurrent call). Confirm all three produce log entries with correct `rejected` and `rejection_reason` values. Confirm `duration_ms` is non-zero for executed commands and zero for rejected/busy requests.
- **Files:** `server.py` (modify), `tests/test_server.py` (modify)

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
