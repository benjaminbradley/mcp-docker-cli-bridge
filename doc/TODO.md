# Implementation Plan — MCP Docker CLI Bridge

> **Status:** Active — Phases 0, 1, 1.5, 2 complete. Next: Phase 3 (Integration Verification) — requires `make down && make up` to apply docker-compose.yml fix first.
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

- [x] Create `Dockerfile` (base stage: MCP SDK deps + server.py + non-root user; dev stage: adds pytest, ruff, mypy, pytest-asyncio)
- [x] Create `docker-compose.yml` (service `my-app`, port `127.0.0.1:7357:7357`, volumes: `commands.dev.json:ro`, `data/bridge-logs`, `server.py`, `tests/`)
- [x] Create `commands.dev.json` (e2e test whitelist: `echo_test`, `run_tests`, `run_lint`, `run_typecheck`, `run_format_check`, `sleep_test`)
- [x] Create `Makefile` (`help`, `build`, `up`, `down`, `logs`, `test`, `lint`, `typecheck`, `format`, `shell`)
- [x] Create `.mcp.json` (registers `http://my-app:7357/mcp` as `bridge-dev` MCP server)
- [x] **Verify:** `make build` ✅ · `make up`/`make logs` (banner) ✅ · `make down` ✅ · `make test` (7 passing) ✅ · `bridge-dev` tools discovered ✅ · invalid config errors ✅
- **Files:** `Dockerfile`, `docker-compose.yml`, `commands.dev.json`, `Makefile`, `.mcp.json`

### 0.1 — Create requirements.txt

> **Infrastructure task — no TDD cycle.** This task installs dependencies with no testable logic. Verification is manual (`pip install`).

- [x] Create `requirements.txt` at project root with `mcp>=1.1.0` and pydantic and any other dependencies imported directly by the app (don't rely on mcp to pull them in).
- [x] **Verify:** `make build` confirmed MCP SDK and pydantic install correctly.
- **Files:** `requirements.txt`

### 0.2 — Create server.py with pydantic models and config loader

- [x] **RED:** In `tests/test_server.py`, add class `TestCommandsConfig`. Write tests covering:
  - `test_valid_config_parses_correctly` — a fully-populated `CommandsConfig` dict round-trips through the model with correct field values.
  - `test_missing_required_field_raises` — omitting `command` from a `CommandEntry` raises `ValidationError`.
  - `test_wrong_type_for_command_raises` — setting `command` to a string (not list) raises `ValidationError`.
  - `test_empty_command_array_raises` — setting `command` to `[]` raises `ValidationError` with message matching "non-empty".
  - `test_effective_timeout_uses_per_command_override` — a command with `timeout=30` and `default_timeout=60` returns `30` from `effective_timeout()`.
  - `test_effective_timeout_falls_back_to_default` — a command with `timeout=None` and `default_timeout=60` returns `60` from `effective_timeout()`.
  - `test_default_timeout_defaults_to_60` — `CommandsConfig` with no `default_timeout` field has `default_timeout == 60`.
  Run `pytest tests/ -v`, confirm all new tests fail with `ImportError` or `ModuleNotFoundError` (right reason: `server.py` does not exist yet).
- [x] **GREEN:** Create `server.py` with: pydantic models (`BridgeConfig`, `CommandEntry`, `CommandsConfig`, `CommandResult`, `LogEntry`) per SPECS.md §6.1; `load_config()` factory reading `BRIDGE_*` env vars; `load_commands(path)` parsing JSON into `CommandsConfig`. Run `pytest tests/ -v`, confirm all `TestCommandsConfig` tests pass.
- [-] **REFACTOR:** No refactoring needed — models are clean as written.
- [x] **Verify (0.0 + 0.2 combined):** All checks passing — `make build` ✅ · banner ✅ · `make test` (7/7) ✅ · `bridge-dev` tools discovered ✅ · invalid config errors ✅
- **Files:** `server.py` (create), `tests/test_server.py` (create)

### 0.3 — Tool registration and tools/list

- [o] **RED:** In `tests/test_server.py`, add class `TestBuildTools`. Write tests covering:
  - `test_builds_one_tool_per_command` — `build_tools(config)` returns a list with the same number of tools as commands in `config`.
  - `test_tool_name_matches_command_name` — each tool's `name` matches its key in `commands`.
  - `test_allow_extra_args_true_includes_args_in_schema` — a command with `allow_extra_args=True` produces a tool whose `inputSchema.properties` contains an `args` key with `type: array, items: {type: string}`.
  - `test_allow_extra_args_false_has_empty_schema` — a command with `allow_extra_args=False` produces a tool whose `inputSchema.properties` is empty (`{}`).
  - `test_description_format` — tool description is `"Execute: "` followed by the command array joined by spaces.
  Run `pytest tests/ -v`, confirm new tests fail because `build_tools` does not exist yet (right reason: `AttributeError` or `ImportError`).
- [o] **GREEN:** Implement `build_tools(config)` per SPECS.md §1.2: generate MCP tool definitions from `CommandsConfig`. Create MCP Server instance, register tools, configure Streamable HTTP transport on `BRIDGE_HOST:BRIDGE_PORT`. Run `pytest tests/ -v`, confirm all `TestBuildTools` tests pass.
- [-] **REFACTOR:** N/A — `build_tools` is clean; `_register_tools` extracted as a named function.
- [x] **Verify:** Server starts without TypeError. `tools/list` returns correct schemas. (FastMCP.run() host/port bug fixed as part of 1.2-1.4 implementation.)
- **Files:** `server.py` (modify), `tests/test_server.py` (modify)

---

## Phase 1 — Command Execution and Concurrency Guard

**Goal:** Tool calls resolve command names, validate arguments, run subprocesses with per-command timeouts, and return `CommandResult` as structured MCP tool results. Concurrent calls are rejected with a retry message. All error paths return proper MCP tool errors.

### 1.1 — Concurrency guard

- [-] **Deferred:** Concurrency guard implemented as part of 1.4 (module-level `asyncio.Lock` + `_current_command`). `test_busy_rejection_returns_is_error` covers the core behavior. Dedicated `TestConcurrencyGuard` with lock-release test deferred — cover in Phase 2 integration if needed.
- [x] **Verify:** Covered by `test_busy_rejection_returns_is_error` unit test; lock + `_current_command` wired into every tool handler.
- **Files:** N/A (implemented)

### 1.2 — Argument validator

- [x] **RED:** `TestValidateArgs` (11 tests) written and confirmed failing.
- [x] **GREEN:** `validate_args()` with `BLOCKED_SEQUENCES` constant. All 11 tests passing.
- [-] **REFACTOR:** N/A — already extracted as named constant.
- [x] **Verify:** 34/34 tests passing.
- **Files:** `server.py` (modify), `tests/test_server.py` (modify)

### 1.3 — Executor

- [x] **RED:** `TestExecuteCommand` (5 tests) written and confirmed failing.
- [x] **GREEN:** `execute_command()` with `subprocess.run(shell=False)`. All 5 tests passing.
- [-] **REFACTOR:** N/A — clean as written.
- [x] **Verify:** 34/34 tests passing.
- **Files:** `server.py` (modify), `tests/test_server.py` (modify)

### 1.4 — Wire executor into tool handlers

- [x] **RED:** `TestToolHandlers` (6 tests) written and confirmed failing.
- [x] **GREEN:** `_create_tool_handler()` with lock check, validate_args, execute_command, exception-based isError. All 6 tests passing.
- [-] **REFACTOR:** N/A — clean as written.
- [x] **Verify (success path):** All bridge-dev MCP tools called from Claude Code — `echo_test`, `run_tests`, `run_lint`, `run_typecheck`, `run_format_check`, `run_format` — all returned correct `{stdout, stderr, exit_code}` JSON.
- [x] **Verify (error paths):** Covered by unit tests (`test_metacharacter_args_return_is_error`, `test_exec_failure_returns_is_error`).
- **Files:** `server.py` (modify), `tests/test_server.py` (modify)

---

## Phase 1.5 — Docker Network Setup (prerequisite for e2e verify)

- [x] Add named network `bridge-dev` with fixed IPAM subnet `172.21.0.0/24` to `docker-compose.yml`
- [x] Add `172.21.0.0/24` allow rule to `.devcontainer/init-firewall.sh`; rebuild devcontainer
- [x] Connect Claude Code container to `bridge-dev` network (`docker network connect bridge-dev <container>`)
- [x] Confirmed `http://my-app:7357/mcp` resolves from Claude Code container; bridge-dev tools appear in Claude Code
- [x] **Bonus:** Added `run_format` tool to `commands.dev.json` (`allow_extra_args: true` — validates the extra-args path e2e)
- [x] **Bonus:** Added `.git/hooks/pre-commit` (Node.js, calls bridge tools via MCP HTTP — no docker dependency)
- [x] **Bonus:** Added `format-check` and `validate` Makefile targets for host-side use

---

## Phase 2 — Request Logging

**Goal:** Every tool invocation (successful, rejected, or busy) is logged to a JSONL file with full request/response payloads per SPECS.md §4.

### 2.1 — Implement log_request

- [x] **RED:** `TestLogRequest` (4 tests) written and confirmed failing.
- [x] **GREEN:** `log_request()` using `Path.mkdir(parents=True, exist_ok=True)` + open/close per write. 43/43 passing.
- [-] **REFACTOR:** N/A — already clean.
- [x] **Verify:** Inspected `data/bridge-logs/bridge.jsonl` via jq. All entries are valid JSON with all expected fields. Validation rejection has `rejected: true`, `rejection_reason` set, `exit_code: null`, `duration_ms: 0`, `stdout_bytes: 0`.
- **Files:** `server.py`, `tests/test_server.py`, `tests/conftest.py`, `tests/server.py`

### 2.2 — Integrate logging into tool handlers

- [x] **RED:** `TestLogIntegration` (5 tests) written and confirmed failing.
- [x] **GREEN:** `_create_tool_handler` now accepts `log_dir`/`log_file`; logs all paths (success, validation rejection, busy rejection) using `LogEntry` + `time.monotonic()` for duration. 43/43 passing.
- [-] **REFACTOR:** N/A — handler is clean; all paths covered.
- [x] **Verify:** Successful calls log correctly (`rejected: false`, non-zero `duration_ms`, correct byte counts). Validation rejection logs correctly (`rejected: true`, `rejection_reason` with disallowed chars, `duration_ms: 0`). Busy rejection: unit-tested only — `subprocess.run` blocks the asyncio event loop so concurrent HTTP requests are serialized; the lock is always free by the time a second request is processed. Deferred to improvements: use `asyncio.to_thread` to make busy rejection triggerable via real HTTP.
- **Files:** `server.py`, `tests/test_server.py`, `tests/server.py`

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
