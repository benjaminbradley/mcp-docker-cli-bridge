# Implementation Workflow

## The Implementation Cycle

```
┌─────────────────────────────────────────────────┐
│  1. Pick task from TODO.md                      │
│  2. Create mini-plan in TASKLOG                 │
│  3. Write failing test (RED)                    │
│  4. Implement (GREEN)                           │
│  5. Refactor (if needed)                        │
│  6. Quick review                                │
│  7. Commit                                      │
│  8. Update TASKLOG + TODO.md                    │
│  9. Loop until TODO.md complete                 │
└─────────────────────────────────────────────────┘
```

## Cycle Sizing

Each cycle should be sized similarly to a single "ticket" assigned to a human developer:
- **Target:** 5-15 minutes per task
- **Grouping:** Tiny similar tasks may be grouped for efficiency
- **Balance:** Small enough for early issue detection, large enough to avoid excessive overhead
- **Commits:** At least one commit per cycle, potentially more (e.g., refactor → feature)

## Step Details

### 1. Pick Task
- Choose the next uncompleted task from TODO.md
- Respect dependencies (don't skip ahead)
- If blocked, note it in TASKLOG and pick another
- Verify prerequisites are met
- **Check `doc/LESSONS.md` Deferred Opportunities** for any items whose domain matches this task. If a match exists with recurrence ≥ 2, escalate its priority before starting. If recurrence ≥ 3, consider resolving the deferred learning first.

### 2. Create Mini-Plan
Add entry to TASKLOG-*-CURRENT.md:

```markdown
## Task [ID]: [Description]
**Status:** 🔄 In Progress
**Started:** [timestamp]

### Mini-Plan
- **Goal:** [One sentence - what does success look like?]
- **Approach:** 
  - [Step 1]
  - [Step 2]
  - [Step 3]
- **Tests:** [What tests will prove this works]
- **Files:** [Files to create/modify]
```

**Commit mini-plan:**
```bash
git add TASKLOG-*-CURRENT.md
git commit -m "docs(tasklog): add plan for task [ID]"
```

See: `templates/TASKLOG.md.template` for full format

### 3. Write Failing Test (RED)
- Describe the expected behavior
- Run test, confirm it fails
- Failure must be meaningful (not syntax error)
- **Update TASKLOG:** Mark RED phase complete

**Example verification:**
```
✓ Expected calculateTotal([10, 20]) to equal 30, got undefined
✗ Good failure - function returns undefined instead of sum

✗ calculateTotal is not defined  
✗ Bad failure - syntax error, not behavioral failure
```

**If refactoring needed first:**
Refactor existing code to support the new feature, commit separately:
```bash
git add [refactored-files]
git commit -m "refactor(scope): prepare for [feature]"
```
Then write test.

**Commit test:**
```bash
git add [test-files]
git commit -m "test(scope): add test for [behavior]"
```

### 4. Implement (GREEN)
- Write the MINIMUM code to pass the test
- Don't optimize yet
- Don't handle edge cases not covered by tests
- Run tests frequently
- **Update TASKLOG:** Mark GREEN phase complete

**Guidelines:**
- Ugly code that passes > elegant code that doesn't exist
- Feature creep is not allowed - stick to task scope
- If you discover additional needs, add to TODO.md

**Commit implementation:**
```bash
git add [implementation-files]
git commit -m "feat(scope): implement [behavior]"
```

### 5. Refactor (if needed)
- Only refactor when tests are GREEN
- Run tests after each small change
- If tests break, undo immediately
- Improve readability, remove duplication
- Extract functions if clarity improves
- **Update TASKLOG:** Mark REFACTOR phase complete or N/A

**Commit refactoring:**
```bash
git add [refactored-files]
git commit -m "refactor(scope): extract [what] for clarity"
```

### 6. Quick Review
Run pre-commit checks:

**Quick Review Checklist:**
- [ ] All tests pass (X new, Y total)
- [ ] No linting errors
- [ ] No debug code left (console.log, print statements)
- [ ] Naming is clear and descriptive
- [ ] No type errors (if applicable)

**If any check fails:** Fix before committing. Quick review **blocks commits** - maintain TDD rigor.

See: `core/workflow/review.md` for full review process

### 7. Update TASKLOG + TODO.md
Finalize task entry in TASKLOG:

```markdown
### Review Results
**Quick Review:**
- [x] Tests pass (3 new, 47 total)
- [x] No linting errors
- [x] No debug code left
- [x] Naming is clear

**Issues Found:** None

### Outcome
**Completed:** [timestamp]
**Duration:** 12 minutes
**Commits:**
- `abc1234` - docs(tasklog): add plan for task 1.2
- `def5678` - test(validators): add email validation tests
- `ghi9012` - feat(validators): implement email validation

**Learnings:** Regex approach simpler than parser library
```

Mark task done in TODO.md: `- [ ]` → `- [x]`

**Commit documentation updates:**
```bash
git add TASKLOG-*-CURRENT.md TODO.md
git commit -m "docs: complete task [ID] - [brief description]"
```

### 8. Commit
Already done in steps 2-5 above. Verify all commits are complete:
- Mini-plan committed
- Test committed (if new test)
- Implementation committed
- Refactoring committed (if applicable)

### 8.5. Lightweight Reflection Scan

While the task's conversation is fresh, scan for signals that may indicate a guideline gap. ~1 minute when signals found, ~10 seconds when not.

**Scan conversation history for:** approach pivots, multi-edit files (corrective, not refactoring), unplanned steps, error → fix sequences, multiple attempts at the same goal.

**Triage each signal:** lesson clear + target file obvious → apply in-place, commit, notify if autocode-level. Otherwise → defer to `doc/LESSONS.md`, add low-priority TODO item.

**Update TASKLOG:** Add `Signals noted` and `Reflection` fields (see `templates/TASKLOG.md.template`).

For full signal definitions, triage process, and output formats see: `core/workflow/reflection.md`

### 9. Loop
Return to step 1, pick next task

## Phase Completion and TASKLOG Rotation

When all tasks in a phase are complete, archive the current TASKLOG and prepare for the next phase.

### Archive Current TASKLOG

```bash
# Rename CURRENT to show task range
git mv TASKLOG-1.1-CURRENT.md TASKLOG-1.1-1.8.md

# Commit the archive
git add TASKLOG-1.1-1.8.md
git commit -m "docs: archive TASKLOG for phase 1 (tasks 1.1-1.8)"
```

**Why `git mv`?**
Preserves the complete git history of all task entries through file rename tracking.

### Start Next Phase TASKLOG

See `core/workflow/planning.md` for initializing TASKLOG for new phases.

### Subdividing Large Phases

If a phase has many tasks (>15), subdivide mid-phase to keep active TASKLOG manageable:

```bash
# Archive first batch
git mv TASKLOG-1.1-CURRENT.md TASKLOG-1.1-1.15.md
git commit -m "docs: archive TASKLOG batch 1 (tasks 1.1-1.15)"

# Start new TASKLOG for remaining tasks
cp templates/TASKLOG.md.template TASKLOG-1.16-CURRENT.md
# Update header with phase info
git add TASKLOG-1.16-CURRENT.md
git commit -m "docs: initialize TASKLOG batch 2 (starting 1.16)"
```

**Benefits:**
- Active TASKLOG stays ~2,000-3,000 lines (10-15 tasks)
- Archived TASKLOGs not loaded unless needed
- Git history provides searchability without loading files

## Verification Checkpoints

Before moving to next task, verify:
- [ ] All tests pass
- [ ] All code is committed
- [ ] TASKLOG entry is complete
- [ ] TODO.md task is marked done
- [ ] No uncommitted changes (unless intentional WIP)
- [ ] No new linting errors
- [ ] No type errors (if applicable)

## Handling Failures

### Test Won't Pass
1. Re-read the test - is it correct?
2. Re-read requirements - understood correctly?
3. Check for typos, off-by-one errors
4. Add debug output to understand behavior
5. If stuck > 10 minutes, ask for help

**Document in TASKLOG:**
```markdown
### TDD Cycle
- RED: ✅ Test written and failing
- GREEN: ⚠️ Issue: Test won't pass after 10 min, requesting help
```

### Unexpected Behavior
1. Don't just "fix it"
2. Understand WHY it happened
3. Add test that catches the issue
4. Then fix
5. Document discovery in TASKLOG learnings

### Scope Creep
If you notice something else that needs fixing:
1. Add it to TODO.md as new task
2. Note it in current TASKLOG entry
3. Don't fix it now - stay focused on current task unless it blocks progress

## Status Check

At session start, verify:

### Code State
- [ ] Working directory clean (or changes understood)
- [ ] On correct branch
- [ ] Tests passing
- [ ] No uncommitted work (check git status)

### Documentation State
- [ ] TODO.md reflects current plan
- [ ] TASKLOG-*-CURRENT.md exists and is up to date
- [ ] HANDOFF.md reviewed (if exists)

### Alignment
- [ ] Next task is clear
- [ ] No blockers
- [ ] Dependencies satisfied

## Anomaly Detection

Flag when:
- Task duration exceeds estimate by 2x
- Tests decreasing instead of increasing
- Many tasks added mid-implementation (scope creep)
- Frequent blockers on simple tasks
- Pattern of TDD violations

**Document in TASKLOG** under learnings and report to human.

## Just-In-Time TDD Verification

After GREEN phase, before REFACTOR, quick check:

### Quick TDD Validation
- [ ] Test file existed before implementation (check git log)
- [ ] Test failed before implementation (you verified this)
- [ ] Test now passes

**❌ If any fail:** Stop, fix the workflow violation immediately.

This catches TDD violations early, before full commit-time verification.

## Full TDD Compliance Verification

Before every commit with production code changes.

### Verification Checklist

#### 1. Test Existence
For every production code change:
- [ ] Corresponding test exists
- [ ] Test was written BEFORE implementation (check git history)
- [ ] Test file follows naming convention

#### 2. Test Quality
For each test:
- [ ] Tests behavior, not implementation
- [ ] Has clear, descriptive name
- [ ] Contains meaningful assertions
- [ ] Tests one concept per test
- [ ] Uses arrange-act-assert pattern

#### 3. Red-Green-Refactor Cycle
Check git history for evidence of:
- [ ] Test commits before implementation commits
- [ ] Small, incremental commits
- [ ] Refactoring commits separate from feature commits

#### 4. Coverage
- [ ] New code paths have tests
- [ ] Edge cases are tested
- [ ] Error conditions are tested

### TDD Violations

**Critical (Block Commit)**
- Production code without tests
- Tests added after implementation
- Tests that pass without implementation (false positives)

**Warning (Note for Review)**
- Tests that mock too much
- Tests coupled to implementation details
- Large test methods

### Recovery Actions

If TDD violations found:

1. **Missing tests**: Write tests for the code
2. **Tests after code:** 
   - Stash implementation
   - Write tests that fail
   - Reapply implementation
   - Verify tests pass
3. **Poor test quality:**
   - Refactor tests to test behavior
   - Remove implementation coupling

## Related Files

- `workflow/tdd.md` - Detailed TDD process
- `workflow/planning.md` - Planning and mini-planning
- `workflow/review.md` - Full review process
- `templates/TASKLOG.md.template` - TASKLOG entry template
