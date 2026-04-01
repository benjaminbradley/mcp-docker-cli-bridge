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
**Status:** 🔄 In Progress
**Started:** 2026-04-01

### Mini-Plan
- **Goal:** `pip install -r requirements.txt` installs the MCP SDK and pydantic in a clean venv.
- **Approach:**
  - Declare `mcp>=1.1.0` (MCP SDK + transitive deps: pydantic, starlette, uvicorn)
  - Declare `pydantic>=2.0` explicitly (imported directly by server.py per ADR 002)
- **Tests:** Infrastructure task — no TDD cycle.
- **Files:** `requirements.txt`

---
