# Planning Workflow

## Two Levels of Planning

### Full Planning (Project/Phase Start)
Create TODO.md with complete task breakdown for entire project or phase.

### Mini-Planning (Task Start)
Create focused plan for single task in TASKLOG.

## Before You Code

Never start coding without a plan. Even "quick fixes" benefit from 30 seconds of thought.

**Full plan** for projects/phases → TODO.md
**Mini-plan** for individual tasks → TASKLOG

## Input Documents

### Required
- **REQUIREMENTS.md** - What to build (features, user stories)

### Recommended
- **ARCHITECTURE.md** - System structure, components, data flow
- **SPECS.md** - API contracts, data schemas, interfaces

### If Missing
Ask the human to provide them, or offer to help create them.

## Full Planning: Creating TODO.md

Break work into small, testable tasks. Each task should:
- Take 5-15 minutes to complete
- Be independently testable
- Have clear acceptance criteria
- Follow dependency order

### Format
```markdown
# Implementation Plan

## Overview
[Brief description of what we're building]

## Tasks

### Phase 1: Foundation
- [ ] Task 1: [Description]
  - Test: [What test proves this works]
  - Files: [Files to create/modify]
- [ ] Task 2: [Description]
  ...

### Phase 2: Core Features
- [ ] Task 3: [Description]
  ...

## Dependencies
- Task 2 depends on Task 1
- Phase 2 depends on Phase 1

## Open Questions
- [Any unclear requirements]
```

## Mini-Planning: Task-Level Plans

Before executing each task, create a mini-plan in TASKLOG-*-CURRENT.md:

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

### Mini-Plan Guidelines

**Keep it lightweight:**
- Goal: Single sentence outcome
- Approach: 2-4 specific steps
- Tests: Clear verification criteria
- Files: Concrete file paths

**When to create:**
After picking task from TODO.md, before writing any code

**Commit mini-plan:**
```bash
git add TASKLOG-*-CURRENT.md
git commit -m "docs(tasklog): add plan for task [ID]"
```

See: `templates/TASKLOG.md.template` for full format

## Initializing TASKLOG

After creating TODO.md and getting approval, initialize TASKLOG for the first phase.

### TASKLOG Naming Convention

**Active TASKLOG:**
```
TASKLOG-[firstId]-CURRENT.md
```

Examples:
- `TASKLOG-1.1-CURRENT.md` - Starting from task 1.1
- `TASKLOG-2.1-CURRENT.md` - New phase starting from task 2.1

**Archived TASKLOG:**
```
TASKLOG-[firstId]-[lastId].md
```

Examples:
- `TASKLOG-1.1-1.8.md` - Completed phase 1, tasks 1.1 through 1.8
- `TASKLOG-2.1-2.5.md` - Completed phase 2, tasks 2.1 through 2.5

### Creating Initial TASKLOG

```bash
# Copy from template
cp templates/TASKLOG.md.template TASKLOG-1.1-CURRENT.md

# Edit file to add phase information in header:
# ## Overview
# **Phase:** Phase 1: Foundation
# **Started:** 2024-01-15

# Commit
git add TASKLOG-1.1-CURRENT.md
git commit -m "docs: initialize TASKLOG for phase 1"
```

### When Starting New Phase

When beginning a new phase (after archiving the previous TASKLOG):

```bash
# Copy from template
cp templates/TASKLOG.md.template TASKLOG-2.1-CURRENT.md

# Update header with new phase info
# Commit
git add TASKLOG-2.1-CURRENT.md
git commit -m "docs: initialize TASKLOG for phase 2"
```

See: `core/workflow/implementation.md` for TASKLOG rotation and archiving

## Getting Approval (Full Plans)

Before implementing:
1. Present the plan to human
2. Explain key decisions and tradeoffs
3. Ask if anything is missing or wrong
4. Get explicit "go ahead" before coding

## Updating the Plan

Plans change. When they do:
1. Update TODO.md with new/changed tasks
2. Mark completed tasks with [x]
3. Note any deferred items
4. Communicate changes to human

## For Existing Codebases

When adding to existing code:
1. Explore the codebase first
2. Understand current patterns and conventions
3. Note existing test patterns
4. Plan to follow existing style
5. Identify integration points

---

## Plan Validation

After creating TODO.md, validate it meets quality standards before proceeding.

### Validation Checklist

#### 1. Completeness

**Required Sections**
- [ ] Overview/goal description
- [ ] Task breakdown
- [ ] Dependencies noted
- [ ] Open questions listed (if any)

**Task Requirements**
- [ ] Each task has clear description
- [ ] Each task has test criteria
- [ ] Each task has estimated scope (5-15 min)
- [ ] Files to modify are identified

#### 2. Task Quality

**Size**
- [ ] Tasks are small (5-15 minutes each)
- [ ] No task requires more than ~50 lines of code
- [ ] Complex tasks are broken down

**Clarity**
- [ ] Task can be understood without additional context
- [ ] Acceptance criteria is verifiable
- [ ] No ambiguous language ("maybe", "might", "could")

**Testability**
- [ ] Test approach is specified
- [ ] Expected behavior is clear
- [ ] Edge cases are considered

#### 3. Ordering

**Dependencies**
- [ ] Dependencies are explicit
- [ ] No circular dependencies
- [ ] Foundation tasks come first
- [ ] Tests can be written before implementation

**Logical Flow**
- [ ] Tasks build on each other
- [ ] Integration points are identified
- [ ] No orphan tasks

#### 4. Alignment

**With Requirements**
- [ ] All requirements are covered
- [ ] No scope creep (unrequested features)
- [ ] Priorities match stakeholder input

**With Architecture**
- [ ] Follows existing patterns
- [ ] Respects module boundaries
- [ ] Doesn't introduce unnecessary coupling

### Red Flags

**Critical Issues**
- Task too large: "Implement the entire feature"
- Vague criteria: "Make it work well"
- Missing tests: No test specification
- Skipped steps: Assumes undone work is done

**Warnings**
- Ambitious estimates
- Many open questions
- Dependencies unclear
- Missing error handling tasks

### Validation Output Format

```markdown
## Plan Validation Report

### Plan: [TODO.md title]

### Structure Check
- Overview: ✅/❌
- Tasks: X defined
- Dependencies: ✅/❌
- Questions: X open

### Task Analysis
| Task | Size | Testable | Clear | Issues |
|------|------|----------|-------|--------|
| 1.1  | ✅   | ✅       | ✅    | None   |
| 1.2  | ⚠️   | ✅       | ❌    | Vague  |

### Issues Found

#### Critical
- [Task X]: [Issue description]

#### Warnings
- [Task Y]: [Issue description]

### Recommendations
1. [Specific action to fix critical issues]
2. [Specific action to address warnings]

### Verdict
READY / NEEDS_REVISION / MAJOR_ISSUES

[Explanation of verdict]
```

### Revision Guidance

When plan needs revision:

1. **Task too large**: Break into 2-3 smaller tasks
2. **Vague criteria**: Add specific, testable conditions
3. **Missing dependencies**: Trace what each task needs
4. **Scope creep**: Remove or defer unrequested items
5. **Missing tests**: Add test specification for each task
