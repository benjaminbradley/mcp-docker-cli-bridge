# /project:plan - Create Full Implementation Plan

Generate a complete implementation plan (TODO.md) for project or phase following TDD workflow.

**Note:** This creates a FULL plan (TODO.md). For individual task plans, see mini-planning in TASKLOG via `/project:task-cycle`.

## Instructions

1. Read requirements documentation:
   - ARCHITECTURE.md (if exists)
   - REQUIREMENTS.md (if exists)
   - SPECS.md (if exists)

2. If requirements are unclear or missing:
   - Ask the human for clarification
   - Offer to help create missing documentation

3. Follow the complete planning workflow:
   @.autocode/core/workflow/planning.md

4. Validate the plan using the checklist in planning.md before presenting

5. Present plan to human for approval before proceeding

## Output

Present the plan with:
- Overview of work
- Phased task breakdown (5-15 min tasks)
- Test requirements for each task
- Dependencies noted
- Open questions listed
- Validation status

Wait for explicit approval before implementing.
