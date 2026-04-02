# TDD Workflow - Detailed Process

## The TDD Cycle

### RED Phase
1. Write a test that describes desired behavior
2. Test MUST fail before writing implementation
3. Verify failure message is meaningful
4. Failure should be for the RIGHT reason (not syntax error)

```
Example of RIGHT failure:
  ✗ Expected calculateTotal([10, 20]) to equal 30, got undefined

Example of WRONG failure:
  ✗ calculateTotal is not defined
```

### GREEN Phase
1. Write the MINIMUM code to pass the test
2. Don't optimize yet
3. Don't handle edge cases not covered by tests
4. Ugly code that passes is better than elegant code that doesn't exist

### REFACTOR Phase
1. Only refactor when tests are GREEN
2. Run tests after each small change
3. If tests break, undo immediately
4. Improve readability, remove duplication
5. Extract functions if clarity improves

## Test Quality

### Good Tests
- Test one behavior per test
- Use descriptive test names: "should reject negative amounts"
- Test through public APIs
- Use factory functions for test data
- Independent - no test depends on another

### Bad Tests
- Testing implementation details
- Multiple assertions testing different behaviors
- Tests that depend on execution order
- Mocking everything
- Testing private methods directly

## Commit Points

Commit after:
- Each passing test + implementation (RED → GREEN)
- Each refactoring step (if tests still green)

Commit message format:
```
test(scope): add test for [behavior]
feat(scope): implement [behavior]
refactor(scope): extract [what] for clarity
```

## Pre-Commit Hooks and the RED Phase

**If the project has a pre-commit hook that runs the test suite, you cannot commit failing tests.** This is a fundamental conflict with the "commit the test first" TDD ideal.

**Resolution:** When a test-running pre-commit hook is present, batch the RED and GREEN commits — write the failing test, implement just enough to pass it, then commit test + implementation together:

```
test(scope): add test for [behavior]     ← written first, not committed yet
feat(scope): implement [behavior]         ← written second
# Both committed together as one or two commits after GREEN
```

This preserves the RED → GREEN discipline in code order, while respecting the constraint that committed tests must pass.

**Do not skip pre-commit hooks (`--no-verify`)** to force-commit failing tests. The hook is protecting the shared history. Accept the batching compromise instead.

## When Tests Are Hard to Write

If a test is hard to write, it usually means:
1. The code is doing too much → Split it
2. Dependencies are tangled → Inject them
3. Requirements are unclear → Ask for clarification

Never skip the test. Fix the design.

## Coverage

- Aim for behavior coverage, not line coverage
- 100% line coverage with bad tests is worthless
- 80% coverage with good behavioral tests is excellent
- Test edge cases: empty inputs, boundaries, errors
