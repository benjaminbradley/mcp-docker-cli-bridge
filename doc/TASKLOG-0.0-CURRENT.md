# TASKLOG — MCP Docker CLI Bridge

## Overview
**Phase:** Phase 0 — MCP Server Skeleton, Models, and Config Loader
**Started:** 2026-04-01
**Tasks:** 0.0 → 0.3

> **Archiving note:** When Phase 0 is complete, archive this file with:
> ```bash
> git mv doc/TASKLOG-0.0-CURRENT.md doc/TASKLOG-0.0-0.3.md
> git commit -m "docs: archive TASKLOG for phase 0 (tasks 0.0-0.3)"
> ```
> `git mv` is required (not a plain rename) to preserve the full git history of all task entries through file rename tracking.

---

## Task 0.0: Dev container setup
**Status:** ✅ Complete
**Started:** 2026-04-01
**Completed:** 2026-04-01

### Mini-Plan
- **Goal:** Docker + Makefile + MCP registration in place so all subsequent TDD cycles run inside the container.
- **Approach:**
  - Create `Dockerfile` (multi-stage: base + dev with test tooling)
  - Create `docker-compose.yml` (service `my-app`, port mapping, volumes)
  - Create `commands.dev.json` (e2e whitelist for self-hosting verification)
  - Create `Makefile` (lifecycle + test/lint/typecheck targets)
  - Create `.mcp.json` (registers bridge-dev at `http://my-app:7357/mcp`)
- **Tests:** Infrastructure task — no TDD cycle.
- **Files:** `Dockerfile`, `docker-compose.yml`, `commands.dev.json`, `Makefile`, `.mcp.json`

### Outcome
**Duration:** Planning session
**Notes:** Verification deferred to end of 0.2 — `make build` requires `requirements.txt` and `server.py` to exist first.

---

## Task 0.1: Create requirements.txt
**Status:** ✅ Complete
**Started:** 2026-04-01
**Completed:** 2026-04-01

### Mini-Plan
- **Goal:** `pip install -r requirements.txt` installs the MCP SDK and pydantic in a clean venv.
- **Approach:**
  - Declare `mcp>=1.1.0` (MCP SDK + transitive deps: pydantic, starlette, uvicorn)
  - Declare `pydantic>=2.0` explicitly (imported directly by server.py per ADR 002)
- **Tests:** Infrastructure task — no TDD cycle.
- **Files:** `requirements.txt`

### Outcome
**Commits:** `569e630` — chore: add requirements.txt with mcp and pydantic
**Notes:** Verify deferred to combined 0.0+0.2 verify gate (requires `make build`).

---

## Task 0.2: server.py — pydantic models and config loader
**Status:** ✅ Complete
**Started:** 2026-04-01
**Completed:** 2026-04-01

### Mini-Plan
- **Goal:** `TestCommandsConfig` passes; `python server.py` prints a correct startup banner.
- **Approach:**
  - RED: write `tests/test_server.py` with 7 `TestCommandsConfig` tests; confirm ImportError
  - GREEN: create `server.py` with all 5 pydantic models + `load_config()` + `load_commands()` + banner in `main()`
  - REFACTOR: N/A — models clean as written
- **Tests:** 7 tests in `TestCommandsConfig` covering model validation and `effective_timeout()`
- **Files:** `server.py` (create), `tests/test_server.py` (create)

### TDD Cycle
- RED: ✅ `tests/test_server.py` written with 7 `TestCommandsConfig` tests; all fail with `ModuleNotFoundError` (server.py not yet created)
- GREEN: ✅ `server.py` created with models + loaders; tests expected to pass
- REFACTOR: N/A

### Review Results
**Quick Review:**
- [x] Tests are meaningful and test behavior not implementation
- [x] No debug code
- [x] Naming is clear
- [x] Models match SPECS.md §6.1 exactly

**Issues Found:** None

### Outcome
**Commits:**
- `5e56f2c` — test(models): add TestCommandsConfig tests
- `a2b0ec0` — feat(models): implement pydantic models and config loader
**Notes:** `make build` + full verify gate ready for human to run.

---
