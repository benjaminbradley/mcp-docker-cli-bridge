# Best Practices

## Code Organization

### File Structure
- One concept per file
- Group related files in directories
- Keep files under 300 lines
- Separate concerns: data, logic, presentation

### Naming
- Variables: describe the value (`userCount`, not `n`)
- Functions: describe the action (`validateEmail`, not `check`)
- Booleans: use is/has/can prefix (`isValid`, `hasPermission`)
- Constants: SCREAMING_SNAKE_CASE

### Functions
- Do one thing
- Take few parameters (≤3 ideal, >5 is a smell)
- Return early to avoid deep nesting
- Pure when possible (same input → same output)

## Error Handling

### Principles
- Fail fast and explicitly
- Provide actionable error messages
- Don't swallow errors silently
- Log errors with context

### Pattern
```
// Good
if (!user) {
  throw new Error(`User not found: ${userId}`);
}

// Bad
if (!user) return null;  // Caller has no idea why
```

## Dependencies

- Minimize external dependencies
- Pin versions for reproducibility
- Evaluate security and maintenance status
- Prefer well-maintained, focused libraries

## Configuration

- No hardcoded values for environment-specific settings
- Use environment variables or config files
- Provide sensible defaults
- Document all configuration options

## Documentation

### Code Comments
- Explain WHY, not WHAT
- Update comments when code changes
- Delete obsolete comments
- Use JSDoc/docstrings for public APIs

### README
- Quick start (get running in 5 minutes)
- Prerequisites
- Installation
- Usage examples
- Configuration options

## Performance

- Don't optimize prematurely
- Measure before optimizing
- Optimize the bottleneck, not everything
- Document performance-critical code

## Security

### Secrets Management
- **Never commit secrets** - use environment variables (`.env`)
- Template file: `.env.example` (committed, no real values)
- Real secrets: `.env` (gitignored, never committed)
- Test setup: Use obviously fake placeholders with clear comments
  ```
  // FAKE-API-KEY-FOR-MOCKED-TESTS-ONLY (not real, external APIs mocked)
  ```
- Load from env: `process.env.API_KEY` or throw error if missing
- Rotate immediately if secret is accidentally exposed
- **Alert immediately on leakage** - if real secrets (not placeholders/variables) are EVER present in context window, ALERT the user IMMEDIATELY and recommend that the credentials be reset/rotated.

### Input Validation
- Validate all external inputs (user, API, file)
- Use parameterized queries (prevent SQL injection)
- Sanitize outputs (prevent XSS)
- Validate file uploads (type, size)

### Authentication & Authorization
- Require authentication for protected resources
- Check authorization before data access
- Use secure session management
- Follow OAuth/OIDC best practices

### Dependencies
- Use latest stable version for additions (search if needed)
- Keep dependencies updated
- Review security advisories
- Minimize attack surface
- Follow principle of least privilege

### Pre-commit Enforcement
- Add `.env*` patterns to `.gitignore` (except `.env.example`)
- Use pre-commit hooks to scan for secrets
- Block commits containing secrets
- Run security linters in CI

### .gitignore Negation Pattern
To ignore a directory's contents but keep specific files (e.g., example configs):
```
config/*                  # ignores contents
!config/_*.example.*      # un-ignores examples
```
**Do not use `config/` (directory match) with negation** — git cannot un-ignore files inside a matched directory. Use `config/*` (glob matching contents) instead.
