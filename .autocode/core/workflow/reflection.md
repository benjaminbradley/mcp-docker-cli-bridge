# Reflection Workflow

## Purpose

The reflection pass converts raw session experience into durable guidelines. It reads conversation history — where the real signals live — and either applies lessons in-place to the source file that governs that domain, or logs the opportunity in `doc/LESSONS.md` for deferred resolution.

**Core principle:** Lessons live in the file that governs the domain where the failure occurred. A preventable linting error gets fixed in `lang/typescript/conventions.md`. A skipped workflow step gets clarified in `core/workflow/implementation.md`. This is DRY applied to the guidelines themselves.

---

## When Reflection Runs

| Mode | Trigger | Scope | Time Budget |
|------|---------|-------|-------------|
| **Lightweight** | After Step 8 of task cycle (Step 8.5) | Current task conversation | ~1 min if signals; ~10s if none |
| **Deep** | Context window warning, `/project:reflect deep`, end of session | Full session conversation | 5-10 min |
| **Phase** | Full Review (pre-PR), `/project:reflect phase` | LESSONS.md + TASKLOG trends | 10-15 min |

The lightweight scan is embedded in `core/workflow/implementation.md` Step 8.5. Deep and phase modes are described in full below.

---

## Step 1: Scan for Signals

Read the conversation history for the relevant scope (task or session). Look for these five patterns:

### Approach Pivots
Direction changed mid-task: "let me try a different approach," "that didn't work," "actually, the issue is…," abandoning a code path mid-implementation.

**May indicate:** Original mini-plan based on incorrect assumption. Guidelines or planning prompts may need to surface this class of assumption.

### Multi-Edit Files
Same file modified more than once during a single task to achieve correctness (corrective edits, not refactoring).

**May indicate:** First edit was wrong. Look for why: unclear convention, incorrect pattern, wrong tool usage.

### Unplanned Steps
Steps taken that were not in the mini-plan — especially tool invocations, file reads, or intermediate fixes required before planned work could proceed.

**May indicate:** Planning prompt missing a prerequisite check, or workflow missing a setup step.

### Error → Fix Sequences
A deterministic tool (test runner, linter, type checker, compiler) reported an error, which was then corrected. **Highest-value signal** — if a deterministic tool caught it, a guideline could have prevented it.

**May indicate:** Identify the exact rule violated and where it should live (see level mapping below).

### Multiple Attempts
Same objective attempted more than once before succeeding (retried tool calls, rewritten functions, revised test assertions).

**May indicate:** Approach unclear, tooling misunderstood, or requirements ambiguous — each points to a different target file.

---

## Step 2: Triage Each Signal

For each signal, answer three questions:

**Q1: Is the lesson clear?**
Can you state in one or two sentences what guideline would have prevented this? If not → defer to LESSONS.md.

**Q2: What level does it belong to?**

| Signal type | Target file | Level |
|---|---|---|
| Linting / formatting error | `lang/{language}/conventions.md` | Language |
| Test structure mistake | `lang/{language}/testing.md` | Language |
| Wrong tool usage | `lang/{language}/tooling.md` | Language |
| Workflow step skipped or out of order | `core/workflow/{relevant}.md` | Core |
| TDD violation pattern | `core/workflow/tdd.md` | Core |
| Communication or clarification failure | `core/collaboration/communication.md` | Core |
| Repeated anti-pattern | `core/principles/anti-patterns.md` | Core |
| Agent-specific behavior | `agents/{agent}/{relevant}.md` | Agent |
| Project-specific code pattern | `doc/LESSONS.md` → Project-Specific section | Project only |
| Lesson unclear or needs more evidence | `doc/LESSONS.md` → Deferred section | Pending |

If genuinely ambiguous, prefer the more specific level (language > core > agent) and note the ambiguity in LESSONS.md.

**Q3: Is it project-specific?**
Does the lesson reference this codebase's structure, domain logic, or specific conventions? If yes → LESSONS.md project-specific section only.

---

## Step 3: Apply or Defer

### Applying In-Place

1. Navigate to the target file (e.g., `.autocode/lang/typescript/conventions.md`)
2. Add the rule, example, or clarification at the most relevant location
3. Keep it concise — one addition addresses one gap
4. Commit: `git add .autocode/[path] && git commit -m "docs(autocode): [description]"`
5. If the file is in `.autocode/` (not project-specific), trigger upstream notification (see below)

### Deferring to LESSONS.md

Add an entry to the Deferred Opportunities table:

```markdown
| [date] | [brief description] | [domain: lang/ts, core/workflow, etc.] | 1 | Low | Open |
```

Add to `TODO.md` as low-priority:
```markdown
- [ ] [LOW] Resolve deferred learning: [brief description] (see doc/LESSONS.md)
```

---

## Step 4: Check for Recurrence

At the **start of each task** (Step 1 of the implementation cycle), scan LESSONS.md Deferred Opportunities for items whose domain matches the current task.

**Recurrence thresholds:**
- Count 2 → Upgrade to Medium priority
- Count 3+ → Upgrade to High priority — resolve before proceeding with related work

---

## Upstream Contribution Protocol

When an in-place edit is made to any `.autocode/` source file (core, language, or agent level):

1. The edit is already committed to the local `.autocode/` copy
2. Log it in LESSONS.md under Upstream Contributions Log
3. Surface to the user in chat:

```
📤 UPSTREAM CONTRIBUTION
File: .autocode/[path/to/file.md]
Change: [one-sentence description]
Rationale: [what happened that revealed this gap]
Action needed: Apply this change to the canonical autocode repository
```

The user decides whether to accept and where to apply it upstream.

---

## Output Formats

### Lesson applied in-place
```
🔧 LESSON APPLIED
File: .autocode/[path/to/file.md]
Change: [description]
Rationale: [what happened in the session]
Commit: docs(autocode): [description]
```

### Opportunity deferred
```
📋 DEFERRED TO LESSONS.md
Description: [opportunity description]
Domain: [lang/ts, core/workflow, etc.]
Reason: [why not applied in-place now]
Recurrence: [count]
```

### No signals found
```
✅ REFLECTION COMPLETE — No signals found
Scanned: [task/session/phase]
```

---

## TASKLOG Integration

After any reflection pass, update the current TASKLOG entry:

```markdown
**Signals noted:** [brief description of corrections/extra steps, or "none"]
**Reflection:** [Applied: .autocode/[file] — [change]] | [Deferred: [description] to LESSONS.md] | [None]
```

---

## Deep Pre-Compact Pass

Context compaction collapses conversation history into a summary. Everything in that history — approach pivots, error sequences, abandoned strategies — is either captured before compaction or lost permanently. **This is the highest-value reflection trigger in the system.**

### Recognizing the Window

Act immediately when any of the following occur:
- Claude Code issues a context length warning
- The `/compact` command is about to be run
- The user mentions context is running long
- Many tasks completed without a deep pass
- About to start a new session (end-of-session = same trigger)

### Protocol

Time-box the full pass to 10 minutes if context pressure is high — capture something over nothing.

1. **Scan full conversation** from the beginning for all five signal types (Step 1 above). Keep a running list — do not act yet.
2. **Eliminate duplicates** — cross-reference TASKLOG reflection notes and LESSONS.md for signals already acted on.
3. **Triage remaining signals** (Step 2 above). Prioritize error → fix sequences first (highest signal quality). Defer anything requiring significant deliberation.
4. **Apply in-place edits** before compaction. Commit each with upstream notifications as needed.
5. **Write LESSONS.md deferred entries** for anything that couldn't be cleanly resolved. A rough entry beats nothing.
6. **Update TASKLOG** with summary:
   ```markdown
   **Pre-Compact Reflection:** [N signals found] | [X applied in-place] | [Y deferred to LESSONS.md] | [Z upstream contributions]
   ```
7. **Commit everything:**
   ```bash
   git add doc/LESSONS.md TASKLOG-*-CURRENT.md
   git commit -m "docs: pre-compact reflection pass"
   ```

### Emergency Capture (Time Critically Short)

If context limit is imminent and there is no time for a full pass:

1. Write a single LESSONS.md deferred entry capturing the session summary: what was worked on, what didn't go as planned, what felt uncertain
2. Commit it
3. Note in TASKLOG: `**Pre-Compact Reflection:** Emergency capture only — full triage deferred`

### Post-Compact Continuity

After compaction, at the start of the next task:
1. Read `doc/LESSONS.md` — check Deferred Opportunities for items relevant to upcoming work
2. Read `TASKLOG-*-CURRENT.md` — confirm session state
3. Check recurrence counts on matching deferred items and escalate if warranted

---

## Phase Reflection Sweep

Run as the final step of the Full Review (pre-PR). This is the phase-level pattern pass — looking across the full implementation arc for trends that individual post-task scans may have missed.

1. **Review LESSONS.md Deferred Opportunities**
   - Recurrence ≥ 2: attempt resolution — is the lesson now clear enough for an in-place edit?
   - Recurrence ≥ 3: treat as high priority — resolve or explicitly discard with reasoning
   - Update status column for all reviewed items

2. **Scan for cross-task patterns**
   - Task types that consistently took longer than estimated
   - Error types that recurred across multiple tasks
   - Workflow steps consistently skipped or done out of order
   - Any of these indicate a guideline gap at the workflow or language level

3. **Apply in-place edits** for clear lessons (same protocol as lightweight scan)

4. **Add phase summary to TASKLOG:**
   ```markdown
   ## Phase Reflection Summary
   **Deferred items reviewed:** [N]
   **Resolved:** [N] (links to commits)
   **Discarded:** [N] (with reasons)
   **Upstream contributions this phase:** [N]
   **Cross-task patterns identified:** [description or "none"]
   ```

---

## What LESSONS.md Is For

`doc/LESSONS.md` exists only for what cannot go directly into a source file:

- **Deferred opportunities** — lesson not yet clear, right level ambiguous, or more evidence needed
- **Project-specific learnings** — patterns specific to this codebase that would not generalize
- **Upstream contributions log** — record of changes already applied and reported

It is a triage holding area that should shrink over time. A growing file indicates reflection is being skipped or lessons are accumulating instead of being applied.

See `templates/LESSONS.md.template` for the deployed structure.

---

## Reflection Quality Check

A reflection pass was worthwhile if:
- At least one signal was identified and acted on (edit or defer), OR
- LESSONS.md was checked for recurrence with no match (explicit no-match is useful)

A reflection pass was insufficient if:
- It only noted "things went smoothly" without scanning
- It produced a LESSONS.md entry for something that clearly belongs in a source file
- It deferred something for the third time without escalating priority

---

## Related Files

- `core/workflow/implementation.md` — Step 8.5 runs the lightweight scan inline
- `core/workflow/review.md` — Full Review invokes the phase sweep
- `templates/LESSONS.md.template` — deployed LESSONS.md structure
- `agents/claude-code/commands/reflect.md` — `/project:reflect` slash command
