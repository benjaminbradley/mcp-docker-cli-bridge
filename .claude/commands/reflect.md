# /project:reflect - Reflection Pass

Run a structured reflection pass to extract lessons from session work and apply them in-place to the appropriate source files.

## Usage

```
/project:reflect              # Lightweight scan (post-task default)
/project:reflect deep         # Full session scan (pre-compact)
/project:reflect phase        # Phase-level sweep (pre-PR, reads LESSONS.md trends)
```

## When to Use

- **Before `/compact`** — always run `deep` first; this window is irreplaceable
- **End of session** — run `deep` before closing
- **Feeling uncertain** — if a task was harder than expected, run lightweight immediately after
- **Pre-PR** — run `phase` as part of the Full Review

The post-task lightweight scan runs automatically as Step 8.5 of the task cycle. Use this command for deeper passes or when the automatic step was skipped.

## Modes

**Lightweight** — Scans current task conversation only. ~1 minute when signals found. Produces in-place edits, LESSONS.md deferrals, or nothing (all valid outcomes).

**Deep** — Scans full session conversation. Cross-references existing LESSONS.md deferred items for recurrence. Looks for cross-task patterns. Answers: "what would I tell my past self at the start of this session?" Run before every `/compact`. 5-10 minutes.

**Phase** — Reviews LESSONS.md and TASKLOG trends across the full implementation phase. Resolves deferred items with enough evidence, discards stale ones, identifies cross-phase patterns. 10-15 minutes.

## Process

Follow `core/workflow/reflection.md` for the complete process: signal detection, triage, in-place edit protocol, upstream contributions, and output formats.

## Related Commands

- `/project:task-cycle` — runs lightweight reflection automatically at Step 8.5
- `/project:review` — runs phase reflection as part of Full Review
