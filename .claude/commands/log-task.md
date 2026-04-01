# /project:log-task - Log Task Execution

Append or update task entry in active TASKLOG.

## Purpose

Automate TASKLOG updates during the task execution cycle:
- Add mini-plan entry when starting task
- Update with TDD cycle progress
- Finalize with review results and outcome

## Usage

### Start Task
```
/project:log-task start [taskId]
```

Creates new task entry in TASKLOG-*-CURRENT.md with:
- Task ID and description (from TODO.md)
- Status: In Progress
- Timestamp
- Empty template sections for mini-plan

### Update with Mini-Plan
```
/project:log-task plan [taskId]
```

Agent fills in:
- Goal (one sentence)
- Approach (steps)
- Test strategy
- Files to modify

Commits: `docs(tasklog): add plan for task [taskId]`

### Update TDD Progress
```
/project:log-task tdd [taskId] [phase]
```

Where phase is: red | green | refactor

Updates TDD Cycle section:
- ✅ Marks phase complete
- ⚠️ Notes issues if any

No commit (TDD commits are separate: test, feat, refactor)

### Finalize Task
```
/project:log-task complete [taskId]
```

Agent fills in:
- Review results (runs quick review)
- Completion timestamp
- Duration calculation
- Commit hashes (from git log)
- Prompts for learnings (optional)

Updates TODO.md: marks task done `[x]`

Commits: `docs: complete task [taskId] - [description]`

## Process

### 1. Find Active TASKLOG

```bash
# Should be exactly one file matching pattern
ls TASKLOG-*-CURRENT.md
```

If not found, error: "No active TASKLOG. Create one from template."

### 2. Extract Task Info

From TODO.md, find task matching ID:
```markdown
- [ ] Task 1.2: Add email validation
  - Test: Validate email format with regex
  - Files: src/validators/email.ts, tests/validators/email.test.ts
```

### 3. Populate Template

Use template from `templates/TASKLOG.md.template`

Fill in:
- Task ID and description
- Timestamp (current)
- Sections based on command (start/plan/tdd/complete)

### 4. Update or Append

- If task entry exists → Update in place
- If new task → Append to end of file

### 5. Auto-Capture Data

**For complete:**
- Run test suite: `npm test` or `pytest` (detect from project)
- Parse output for pass/fail counts
- Get recent commits: `git log --oneline -5`
- Calculate duration from start timestamp

## Output Format

### After Start
```
Task 1.2 started in TASKLOG-1.1-CURRENT.md
Ready for mini-planning.
```

### After Plan
```
Mini-plan added for task 1.2
Committed: docs(tasklog): add plan for task 1.2

Ready to begin TDD cycle.
```

### After TDD Update
```
TDD Cycle updated: RED ✅
Continue to GREEN phase.
```

### After Complete
```
Task 1.2 completed!

Results:
- Duration: 12 minutes
- Tests: 3 new, 47 total passing
- Commits: 2 (test + feat)
- Issues: None

Updated:
- TASKLOG-1.1-CURRENT.md
- TODO.md (task marked done)

Committed: docs: complete task 1.2 - email validation
```

## Integration with Task Cycle

Called automatically by `/project:task-cycle`:

```
/project:task-cycle
    ↓
/project:log-task start 1.2
    ↓
Agent creates mini-plan
    ↓
/project:log-task plan 1.2
    ↓
Agent executes TDD (RED)
    ↓
/project:log-task tdd 1.2 red
    ↓
Agent executes TDD (GREEN)
    ↓
/project:log-task tdd 1.2 green
    ↓
Agent executes TDD (REFACTOR if needed)
    ↓
/project:log-task tdd 1.2 refactor
    ↓
Agent runs review
    ↓
/project:log-task complete 1.2
```

## Error Handling

### No Active TASKLOG
```
Error: No active TASKLOG found.
Create TASKLOG-[firstId]-CURRENT.md from template before logging tasks.
```

### Task Not in TODO.md
```
Error: Task 1.2 not found in TODO.md
Verify task ID or add task to TODO.md first.
```

### Task Already Complete
```
Warning: Task 1.2 already marked complete in TODO.md
Use 'update' instead of 'start' to modify entry.
```

## Manual Usage

Can also be called manually for fine-grained control:

```
# Start task, then manually create plan
/project:log-task start 1.2

# Update specific TDD phase
/project:log-task tdd 1.2 green

# Finalize after review
/project:log-task complete 1.2
```

## Notes

- Timestamps use ISO 8601 format: `YYYY-MM-DD HH:MM`
- Duration calculated from start to complete timestamps
- Git log filtered to commits since task start
- Test counts auto-detected from test runner output
