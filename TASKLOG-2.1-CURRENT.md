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
- RED: ✅ 4 tests failing (ImportError — log_request missing)
- GREEN: ✅ 43/43 passing
- REFACTOR: N/A

### Outcome
**Completed:** 2026-04-01
**Commits:** 8c41599 (feat: implement log_request + Docker bind mount fix)

**Learnings:** Docker file bind mounts are inode-based. When the host editor atomically replaces a file (new inode), the container's bind mount still sees the old inode. Workaround: load server module from directory-mounted `tests/server.py` in conftest.py. Long-term fix: docker-compose.yml now has `- .:/workspace` + PYTHONPATH=/workspace; takes effect after `make down && make up`.

---

## Task 2.2: Integrate logging into tool handlers
**Status:** ✅ Complete
**Started:** 2026-04-01

### Mini-Plan
- **Goal:** Every handler path (success, validation error, busy, timeout, exec failure) constructs and writes a `LogEntry`.
- **Approach:**
  1. Extend `TestToolHandlers` or add `TestLogIntegration` tests (logged, rejected, busy, duration)
  2. Wire `log_request` into `_create_tool_handler` via injected `log_dir`/`log_file` params
  3. Capture wall-clock duration with `time.monotonic()`
- **Tests:** 5 tests
- **Files:** `tests/test_server.py` (add tests), `server.py` (modify handler)

### TDD Cycle
- RED: ✅ 5 tests failing (TypeError — `_create_tool_handler` takes 2 args, 4 given)
- GREEN: ✅ 43/43 passing
- REFACTOR: N/A — all handler paths covered; clean as written

### Outcome
**Completed:** 2026-04-01
**Commits:** 466fec2 (feat: integrate log_request into tool handlers)

**Learnings:** `echo` command completes in <1ms so `int(duration_ms)` rounds to 0. Fixed by using `python -c "pass"` in the `duration_ms > 0` test (Python startup guarantees measurable elapsed time).

---

## Phase 2 Summary

All tasks complete. 43/43 tests passing. Docker file bind mount issue discovered and worked around (see task 2.1 learnings). docker-compose.yml updated for proper fix — requires `make down && make up` to take effect. After restart, tests/conftest.py can be simplified (PYTHONPATH=/workspace makes tests/server.py copy unnecessary).

## Deep Reflection — Pre-Compact (2026-04-01)

**Signals found:**
1. Docker file bind mount → inode stale after atomic edit. **Applied in-place** → `docker.md` (new section)
2. Pre-commit hook blocks RED-phase test commits. **Applied in-place** → `tdd.md` (new section)
3. `echo` too fast for `duration_ms > 0` assertion; `python -c "pass"` is the fix. **Applied in-place** → `testing.md` (new "Timing-Sensitive Tests" section)
4. Background agents return stale file state post-edit. **Deferred** → `doc/LESSONS.md`

**What I'd tell past-self:** Start with `docker compose config` and check volume types before any test-failing/import-error debugging. File bind mounts are a footgun when editors use atomic writes. Verify volume type first, save 30 minutes.
