# TASKLOG — Phase 3 prep: asyncio.to_thread fix
**Phase:** Unplanned improvement (pre-Phase 3)
**Started:** 2026-04-02

---

## Task 3.0: Make execute_command async (asyncio.to_thread)
**Status:** 🔄 In Progress
**Started:** 2026-04-02

### Mini-Plan
- **Goal:** `execute_command` runs subprocess in a thread pool so the event loop stays free, enabling concurrent HTTP requests and real busy rejection.
- **Approach:**
  1. Convert `TestExecuteCommand` to async (`@pytest.mark.asyncio`, `async def`, `await execute_command(...)`)
  2. Add `test_concurrent_busy_rejection` to `TestToolHandlers` — two handlers launched as real asyncio tasks simultaneously; second must raise "busy"
  3. Make `execute_command` `async`, wrap `subprocess.run` in `await asyncio.to_thread(...)`
  4. `await execute_command(...)` at the call site in `_create_tool_handler`
- **Tests:** 5 converted + 1 new = 6 test changes
- **Files:** `tests/test_server.py`, `server.py`, `tests/server.py`

### TDD Cycle
- RED: ⏳
- GREEN: ⏳
- REFACTOR: ⏳
