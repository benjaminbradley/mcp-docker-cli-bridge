# Implementation Plan — Docker CLI Access Bridge

> **Status:** Active
> **Created:** 2026-03-31
> **References:** [Requirements](REQUIREMENTS.md) · [Architecture](ARCHITECTURE.md) · [Specs](SPECS.md)

Legend:

`[ ]` = Planned
`[~]` = In progress
`[o]` = Implemented
`[x]` = Verified
`[-]` = Skipped with reason

---

## Phase 0 — Server Skeleton and Config Loader

**Goal:** A running HTTP server that loads and validates `commands.json` on startup. No command execution yet — just startup, config validation, and a stub `/execute` endpoint that returns the list of loaded commands.

### 0.1 — Create server.py with startup and config loader
- [ ] Create `server.py` at project root with: env var loading (all six config vars with defaults per SPECS.md §5), `load_commands(path)` function that reads and validates JSON per SPECS.md §2.3, `main()` that loads config and starts `HTTPServer`.
- [ ] `load_commands` must exit non-zero with a clear error message for: missing file, invalid JSON, missing required fields, wrong types.
- [ ] Startup prints a banner: port, bind address, config file path, number of commands loaded.
- [ ] **Verify:** Create a test `commands.json` with 2-3 entries. Run `python server.py` directly. Confirm banner prints with correct command count. Rename config file and confirm server exits with error.

### 0.2 — Stub /execute endpoint and error routing
- [ ] Implement `BridgeHandler` with `do_POST` routing to `/execute` (returns `{"status": "ok", "commands_loaded": N}` for now) and 404/405 for other paths/methods.
- [ ] Override `log_message` to suppress default stderr access logging.
- [ ] **Verify:** `curl -X POST http://localhost:7357/execute` returns the stub response. `curl http://localhost:7357/execute` (GET) returns 405. `curl -X POST http://localhost:7357/other` returns 404.

---

## Phase 1 — Command Execution

**Goal:** The `/execute` endpoint resolves command names, validates arguments, runs subprocesses, and returns results. All error paths return structured JSON.

### 1.1 — Argument validator
- [ ] Implement `validate_args(args)` per SPECS.md §3: type check (all strings), metacharacter blocklist scan. Returns `None` if valid, error message string if invalid.
- [ ] **Verify:** Call directly in a Python REPL. `validate_args(["--tb=short"])` → `None`. `validate_args(["--flag; rm -rf /"])` → error string. `validate_args([123])` → error string.

### 1.2 — Executor
- [ ] Implement `execute_command(name, args, commands)` per SPECS.md §6: whitelist lookup, `allow_extra_args` check, `validate_args` call, `subprocess.run` with `shell=False`, `capture_output=True`, `text=True`, `timeout`, `cwd`. Return `(http_status_code, response_dict)`.
- [ ] Handle `subprocess.TimeoutExpired` → HTTP 504 with partial output.
- [ ] Handle `FileNotFoundError` → HTTP 500.
- [ ] Handle unknown command → HTTP 400 with available commands list.
- [ ] **Verify:** With a test `commands.json` containing an `echo` command (`["echo", "hello"]`, `allow_extra_args: true`), send `curl -X POST -d '{"command":"echo","args":["world"]}' http://localhost:7357/execute`. Confirm `stdout` contains "hello world", `exit_code` is 0.

### 1.3 — Wire executor into handler
- [ ] Replace the stub `/execute` handler with real logic: parse JSON body, extract `command` and `args` (default `[]`), call `execute_command`, serialize response.
- [ ] Handle malformed JSON → HTTP 400. Handle missing `command` field → HTTP 400.
- [ ] **Verify (success path):** `curl -s -X POST -H 'Content-Type: application/json' -d '{"command":"echo"}' http://localhost:7357/execute | python -m json.tool` returns stdout/stderr/exit_code.
- [ ] **Verify (error paths):** Unknown command returns 400 with available_commands. Extra args on a locked command returns 400. Metacharacter in args returns 400. Malformed JSON returns 400.

---

## Phase 2 — Request Logging

**Goal:** Every request (successful or rejected) is logged to a JSONL file with metadata per SPECS.md §4.

### 2.1 — Implement log_request
- [ ] Implement `log_request(entry, log_dir, log_file)`: construct log entry dict per SPECS.md §4.2, serialize to JSON, append to file with newline, close file handle. Create log directory if it does not exist.
- [ ] **Verify:** After a few curl requests, inspect the log file. Confirm each line is valid JSON with all expected fields. Confirm rejected requests have `rejected: true` and a reason. Confirm stdout/stderr content is NOT in the log (only byte lengths).

### 2.2 — Integrate logging into handler
- [ ] Call `log_request` at the end of every `do_POST` handler path (both success and error). Capture wall-clock duration using `time.monotonic()` around the execution call.
- [ ] **Verify:** Send a successful request and a rejected request. Confirm both produce log entries. Confirm `duration_ms` is non-zero for executed commands and zero for rejected requests.

---

## Phase 3 — Integration Verification

**Goal:** Verify the bridge works end-to-end in its intended deployment context: inside a Docker container on a bridge network, with a consumer project's commands.json.

### 3.1 — Manual integration test with find-work-bot
- [ ] In find-work-bot, create the integration files per SPECS.md §7 and §8: `commands.json`, `docker-compose.dev.yml`, Dockerfile `dev` stage, `doc/DEVELOPMENT.md`, updated `CLAUDE.md`.
- [ ] Start the dev environment: `make dev-up` (to be added to find-work-bot Makefile).
- [ ] **Verify:** From another container on the bridge network (or with the port temporarily published), run:
  - `curl -X POST -H 'Content-Type: application/json' -d '{"command":"run_tests"}' http://<service>:7357/execute` → tests run, stdout shows pytest output, exit_code 0.
  - `curl -X POST -H 'Content-Type: application/json' -d '{"command":"run_lint"}' http://<service>:7357/execute` → ruff output.
  - `curl -X POST -H 'Content-Type: application/json' -d '{"command":"unknown"}' http://<service>:7357/execute` → HTTP 400 with available commands.
  - Inspect `data/bridge-logs/bridge.jsonl` on host → entries present.

### 3.2 — Pre-commit hook
- [ ] Create `scripts/pre-commit` in find-work-bot per SPECS.md §7.4.
- [ ] Document installation in `doc/DEVELOPMENT.md`.
- [ ] **Verify:** With the dev container running, `git commit` triggers lint/typecheck/test via the bridge. A failing check blocks the commit with clear output.

### 3.3 — Makefile dual-mode
- [ ] Update find-work-bot Makefile targets (`test`, `lint`, `typecheck`, `format`) to use the `DEV_RUNNING` detection pattern per SPECS.md §7.3.
- [ ] Add `dev-up` and `dev-down` targets.
- [ ] **Verify:** With dev container running, `make test` uses `exec`. With dev container stopped, `make test` uses `run --rm`. Both produce the same test results.

---

## Deferred

- **Bridge test suite:** Unit tests for server.py (arg validation, config loading, executor). Not blocking MVP — the bridge is verified through manual curl testing and through the consumer project's test suite running over it. Tracked for future hardening.
- **Structured stderr logging:** The server currently suppresses default HTTP access logs. A future enhancement could emit structured JSON to stderr for container log aggregation.
