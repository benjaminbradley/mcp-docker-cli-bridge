# /project:review - Full Review Before PR

Perform comprehensive review of all changes before creating Pull Request.

**Note:** This is a FULL review (comprehensive). For quick task-level reviews, see quick review in task cycle workflow.

## Instructions

1. Follow the complete review workflow:
   @.autocode/core/workflow/review.md

2. Run automated checks:
   - Tests (all must pass)
   - Linting
   - Type checking (if applicable)

3. Apply all checklists from review.md:
   - Code quality checklist
   - Automated review checklist
   - Severity assessment

4. Report findings to human

## Output Format

```markdown
## Code Review Report

### Files Reviewed
- [list files with line counts]

### Summary
- Critical: X
- High: Y
- Low: Z

### Issues
[Categorized by severity]

### Verdict
[APPROVE / REQUEST_CHANGES with specific fixes needed]
```

## Next Steps

Based on review results:
- **APPROVE**: Ready to commit
- **REQUEST_CHANGES**: Fix issues, then re-review
