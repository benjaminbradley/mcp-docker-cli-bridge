# Anti-Patterns - What to Avoid

## Testing Anti-Patterns

### ❌ Testing Implementation, Not Behavior
```
// BAD: Tests internal method
expect(service._validateInternal()).toBe(true);

// GOOD: Tests observable behavior
expect(service.process(validInput)).toEqual(expectedOutput);
```

### ❌ Test Interdependence
```
// BAD: Test 2 depends on state from Test 1
test('creates user', () => { createUser(); });
test('gets user', () => { expect(getUser()).toBeDefined(); });  // Depends on previous

// GOOD: Each test is independent
test('gets user', () => {
  createUser();  // Arrange within test
  expect(getUser()).toBeDefined();
});
```

### ❌ Testing Without Assertions
```
// BAD: No assertion
test('loads data', async () => {
  await loadData();  // What are we verifying?
});

// GOOD: Clear assertion
test('loads data', async () => {
  const data = await loadData();
  expect(data.length).toBeGreaterThan(0);
});
```

## Code Anti-Patterns

### ❌ Deep Nesting
```
// BAD
if (user) {
  if (user.isActive) {
    if (user.hasPermission) {
      if (resource.isAvailable) {
        // actual logic buried here
      }
    }
  }
}

// GOOD: Early returns
if (!user) return;
if (!user.isActive) return;
if (!user.hasPermission) return;
if (!resource.isAvailable) return;
// actual logic at top level
```

### ❌ Magic Numbers/Strings
```
// BAD
if (status === 3) { ... }
setTimeout(fn, 86400000);

// GOOD
const STATUS_APPROVED = 3;
const ONE_DAY_MS = 24 * 60 * 60 * 1000;
if (status === STATUS_APPROVED) { ... }
setTimeout(fn, ONE_DAY_MS);
```

### ❌ God Functions
```
// BAD: Function does everything
function handleRequest(req) {
  // validate (20 lines)
  // transform (30 lines)
  // save (20 lines)
  // notify (15 lines)
  // log (10 lines)
}

// GOOD: Single responsibility
function handleRequest(req) {
  const data = validate(req);
  const transformed = transform(data);
  await save(transformed);
  await notify(transformed);
}
```

### ❌ Boolean Blindness
```
// BAD: What do these booleans mean?
processOrder(order, true, false, true);

// GOOD: Named options
processOrder(order, {
  sendConfirmation: true,
  skipValidation: false,
  priority: true
});
```

## Workflow Anti-Patterns

### ❌ Coding Without Tests
"I'll add tests later" = tests never get added.
Write the test first, always.

### ❌ Big Bang Commits
```
// BAD
git commit -m "Implement entire feature"  // 500 line change

// GOOD
git commit -m "test(users): add test for user creation"
git commit -m "feat(users): implement user creation"
git commit -m "refactor(users): extract validation logic"
```

### ❌ Fixing Multiple Things at Once
One PR = One concern. If you find another bug while working:
1. Note it in TODO.md
2. Finish current task
3. Create separate PR for the other fix

### ❌ Assuming Requirements
```
// BAD
// "I think they probably want it to also handle X"
// Implements unrequested feature

// GOOD
// "Requirements don't specify X. Should I include it?"
// Asks before implementing
```

## Communication Anti-Patterns

### ❌ Hiding Problems
```
// BAD
"Everything is going well" (while stuck for an hour)

// GOOD
"I've been stuck on X for 10 minutes. I've tried A and B. 
Could you help clarify?"
```

### ❌ Sycophancy
```
// BAD
"That's a great idea!" (when it's actually problematic)

// GOOD
"I see some potential issues with that approach:
1. [Specific concern]
2. [Specific concern]
Have you considered [alternative]?"
```
