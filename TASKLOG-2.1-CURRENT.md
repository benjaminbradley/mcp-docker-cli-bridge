# TASKLOG — Phase 2: Request Logging
**Phase:** Phase 2 — Request Logging
**Started:** 2026-04-01

---

## Task 2.1: Implement log_request
**Status:** 🔄 In Progress
**Started:** 2026-04-01

### Mini-Plan
- **Goal:** `log_request(entry, log_dir, log_file)` appends a JSONL line to the log file, creating the file and directory as needed.
- **Approach:**
  1. Write `TestLogRequest` tests (creates file, creates dir, appends, fields present)
  2. Implement `log_request` using `Path.mkdir(parents=True, exist_ok=True)` + open/close per write
  3. Verify tests pass
- **Tests:** 4 tests in `TestLogRequest`
- **Files:** `tests/test_server.py` (add class), `server.py` (add function)

### TDD Cycle
- RED: ⏳
- GREEN: ⏳
- REFACTOR: ⏳

---

## Task 2.2: Integrate logging into tool handlers
**Status:** ⏳ Pending
**Started:** —

### Mini-Plan
- **Goal:** Every handler path (success, validation error, busy, timeout, exec failure) constructs and writes a `LogEntry`.
- **Approach:**
  1. Extend `TestToolHandlers` or add `TestLogIntegration` tests (logged, rejected, busy, duration)
  2. Wire `log_request` into `_create_tool_handler` via injected `log_dir`/`log_file` params
  3. Capture wall-clock duration with `time.monotonic()`
- **Tests:** 5 tests
- **Files:** `tests/test_server.py` (add tests), `server.py` (modify handler)
