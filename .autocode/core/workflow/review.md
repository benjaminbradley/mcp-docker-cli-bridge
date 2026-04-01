# Code Review Workflow

## Two Types of Review

### Quick Review
**When:** Before every task commit (every cycle)
**Purpose:** Catch obvious issues before commit
**Output:** Logged in TASKLOG

### Full Review
**When:** Before creating Pull Request
**Purpose:** Comprehensive quality assessment
**Output:** Formal review report artifact

---

## Quick Review (Every Task)

Run before committing each task. **Failures block commits** - maintain TDD rigor.

### Quick Review Checklist

- [ ] All tests pass (X new, Y total)
- [ ] No linting errors
- [ ] No debug code left (console.log, print, etc.)
- [ ] Naming is clear and descriptive
- [ ] No type errors (if applicable)

### Log Results in TASKLOG

```markdown
### Review Results
**Quick Review:**
- [x] Tests pass (3 new, 47 total)
- [x] No linting errors
- [x] No debug code left
- [x] Naming is clear

**Issues Found:** None
```

**If issues found:**
- Fix before committing
- Document in TASKLOG with severity
- Critical issues block commit

See: `core/workflow/implementation.md` for full task cycle

---

## Full Review (Before PR)

Comprehensive review before creating Pull Request.

Before creating a Pull Request:

### Code Quality
- [ ] Tests pass
- [ ] No linting errors
- [ ] No type errors
- [ ] No console.log / print debugging left
- [ ] No commented-out code
- [ ] No TODO without issue reference

### Test Quality
- [ ] Tests are meaningful (not just coverage)
- [ ] Tests describe behavior, not implementation
- [ ] Edge cases covered
- [ ] Error cases tested

### Readability
- [ ] Names are clear and descriptive
- [ ] Functions do one thing
- [ ] No deep nesting (max 3 levels)
- [ ] Complex logic has comments explaining WHY

### Security (if applicable)
- [ ] No secrets in code
- [ ] Input validation present
- [ ] No SQL injection risks
- [ ] No XSS risks

### Completeness
- [ ] All tasks in TODO.md are marked done
- [ ] TASKLOG-*-CURRENT.md entries are complete
- [ ] Documentation updated if needed
- [ ] README updated if setup changed

### Integration
- [ ] Pulled latest from main
- [ ] Resolved any conflicts
- [ ] Full test suite passes
- [ ] Linting passes on all files

### Commit History
- [ ] Commits are logical units
- [ ] Commit messages are clear
- [ ] No "WIP" or "fix typo" commits (squash them)

## Reflection Sweep (Part of Full Review)

Run as the final step of the Full Review, before creating the PR. This is the phase-level pattern pass — looking across the full implementation arc for trends that individual post-task scans may have missed.

Review LESSONS.md deferred items (resolve or discard those with sufficient evidence), scan for cross-task patterns (recurring error types, consistently skipped steps, tasks that took longer than estimated), apply in-place edits for clear lessons, and add a phase summary to TASKLOG.

For the full phase sweep protocol and output formats see: `core/workflow/reflection.md` (Phase Reflection Sweep section)

---

## Receiving Feedback

When human provides feedback:
1. Read all feedback first before responding
2. Ask clarifying questions if unclear
3. Acknowledge valid points
4. Explain reasoning if you disagree
5. Implement changes systematically
6. Re-run all checks after changes

---

## Automated Code Review

Perform systematic review before every commit.

### Review Checklist

#### 1. Code Quality

**Naming**
- [ ] Variables describe their values
- [ ] Functions describe their actions
- [ ] No single-letter names (except loop indices)
- [ ] No abbreviations without context

**Structure**
- [ ] Functions do one thing
- [ ] Max 3 levels of nesting
- [ ] Files under 300 lines
- [ ] No god classes/functions

**Clarity**
- [ ] No commented-out code
- [ ] No TODO without issue reference
- [ ] Complex logic has comments (WHY, not WHAT)
- [ ] No magic numbers/strings

#### 2. Error Handling
- [ ] Errors handled explicitly
- [ ] Error messages are actionable
- [ ] No swallowed exceptions
- [ ] Appropriate error types used

#### 3. Testing
- [ ] Tests exist for new code
- [ ] Tests are meaningful
- [ ] Edge cases covered
- [ ] Error cases tested

#### 4. Security
- [ ] No secrets in code
- [ ] Inputs validated
- [ ] No SQL injection risks
- [ ] No XSS vulnerabilities (if web)

#### 5. Documentation
- [ ] Public APIs documented
- [ ] README updated if needed
- [ ] Breaking changes noted

#### 6. Git Hygiene
- [ ] Commit message follows convention
- [ ] Atomic commit (one logical change)
- [ ] No unrelated changes

### Severity Levels

**❌ Critical (Block Commit)**
- Security vulnerabilities
- Tests failing
- Obvious bugs
- Secrets in code

**⚠️ High (Should Fix)**
- Missing error handling
- Missing tests
- Code style violations
- Poor naming

**💡 Low (Consider)**
- Minor style issues
- Optimization opportunities
- Documentation improvements

### Review Output Format

```markdown
## Code Review Report

### Files Reviewed
- file1.ts (X lines changed)
- file2.ts (Y lines changed)

### Summary
- Critical: X
- High: Y  
- Low: Z

### Issues

#### ❌ Critical
1. [file:line] [description]

#### ⚠️ High
1. [file:line] [description]

#### 💡 Low
1. [file:line] [description]

### Recommendations
[Specific actions to take]

### Verdict
[APPROVE / REQUEST_CHANGES / NEEDS_DISCUSSION]
```

### Auto-Fixable Issues

Some issues can be auto-fixed:
- Formatting → Run formatter
- Import order → Run isort/eslint
- Trailing whitespace → Configure editor
- Missing semicolons → Run linter --fix

Note which issues were auto-fixed vs need manual attention.
