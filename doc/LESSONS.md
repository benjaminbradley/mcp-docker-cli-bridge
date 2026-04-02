# Lessons

Triage holding area for learning opportunities that cannot yet be applied in-place to a source file.
See `.autocode/core/workflow/reflection.md` for the full system description.

**Principle:** This file should shrink over time. Deferred items resolve into in-place edits to source files or are discarded. A growing file indicates reflection is being skipped or lessons are being accumulated instead of applied.

---

## Deferred Opportunities

Opportunities where the lesson is not yet clear, the right level is ambiguous, or more evidence is needed.

Recurrence thresholds: Count 2 → Medium priority. Count 3+ → High priority (resolve before related work).

| Date | Description | Domain | Recurrence | Priority | Status |
|------|-------------|--------|------------|----------|--------|
| 2026-04-01 | Background agents (e.g. explore agent) can return stale or incorrect file state if the file was recently modified. Agent reads the file as it was before the edit landed. Symptoms: agent reports function missing when it was just added. Workaround: read the file directly (Read tool) instead of delegating to an agent for verification after edits. | Agents / tooling | 1 | Low | Open |

**Status values:** Open · In Progress · Resolved (link to commit) · Discarded (reason)

---

## Project-Specific Learnings

Patterns specific to this codebase, architecture, or domain that would not generalize to other projects. These stay here permanently — they do not belong in autocode source files.

| Date | Description | Applied? |
|------|-------------|----------|
| | | |

---

## Upstream Contributions Log

Record of in-place edits made to `.autocode/` source files and reported to the user for inclusion in the canonical autocode repository.

| Date | File Changed | Change Description | User Notified | Commit |
|------|--------------|--------------------|---------------|--------|
| 2026-04-01 | `.autocode/core/principles/docker.md` | Added "Source File Bind Mounts — Use Directory Mounts, Not File Mounts" section | Pending | 77c84dc (pre-edit) |
| 2026-04-01 | `.autocode/core/workflow/tdd.md` | Added "Pre-Commit Hooks and the RED Phase" section | Pending | 77c84dc (pre-edit) |
| 2026-04-01 | `.autocode/lang/python/testing.md` | Added "Timing-Sensitive Tests" section (use python -c "pass" not shell builtins for duration assertions) | Pending | — |
