# Python Testing

## Framework

Recommended: **pytest**

pytest preferred for:
- Simple test discovery
- Powerful fixtures
- Rich plugin ecosystem
- Clear output

## Test Organization

### File Structure
```
src/
├── myapp/
│   ├── __init__.py
│   ├── services/
│   │   └── user_service.py
│   └── models/
│       └── user.py
tests/
├── __init__.py
├── conftest.py              # Shared fixtures
├── unit/
│   └── test_user_service.py
└── integration/
    └── test_api.py
```

### Test File Structure
```python
"""Tests for user service."""
import pytest
from myapp.services import UserService

class TestUserService:
    """Tests for UserService class."""
    
    class TestCreateUser:
        """Tests for create_user method."""
        
        def test_creates_user_with_valid_data(self):
            # Arrange, Act, Assert
            ...
        
        def test_raises_on_invalid_email(self):
            ...
```

## Naming

```python
# Test classes: Test + ClassUnderTest
class TestUserService:
    
    # Nested class for method grouping
    class TestCreateUser:
        
        # Test methods: test_ + behavior description
        def test_returns_user_with_generated_id(self):
            ...
        
        def test_raises_validation_error_when_email_invalid(self):
            ...
```

## Arrange-Act-Assert

```python
def test_calculates_total_with_tax(self):
    # Arrange
    items = [
        Item(price=100, quantity=2),
        Item(price=50, quantity=1),
    ]
    tax_rate = 0.1

    # Act
    total = calculate_total(items, tax_rate)

    # Assert
    assert total == 275  # (200 + 50) * 1.1
```

## Fixtures

### Basic Fixtures
```python
# conftest.py
import pytest

@pytest.fixture
def user():
    """Create a test user."""
    return User(id="test-id", name="Test User", email="test@example.com")

@pytest.fixture
def user_service(database):
    """Create UserService with test database."""
    return UserService(db=database)
```

### Factory Fixtures
```python
@pytest.fixture
def make_user():
    """Factory fixture for creating users."""
    def _make_user(**overrides):
        defaults = {
            "id": "test-id",
            "name": "Test User",
            "email": "test@example.com",
        }
        return User(**{**defaults, **overrides})
    return _make_user

# Usage
def test_update_user_name(make_user):
    user = make_user(name="Original")
    updated = update_user(user, name="New Name")
    assert updated.name == "New Name"
```

### Scoped Fixtures
```python
@pytest.fixture(scope="session")
def database():
    """Create database once per test session."""
    db = create_test_database()
    yield db
    db.cleanup()

@pytest.fixture(scope="function")  # Default
def clean_db(database):
    """Clean database before each test."""
    database.clear()
    return database
```

## Mocking

### pytest-mock
```python
def test_sends_email_on_registration(mocker):
    mock_send = mocker.patch("myapp.email.send_email")
    
    register_user("test@example.com")
    
    mock_send.assert_called_once_with(
        to="test@example.com",
        subject="Welcome!"
    )
```

### Dependency Injection (Preferred)
```python
def test_creates_user(make_user):
    mock_db = Mock()
    mock_db.save.return_value = True
    service = UserService(db=mock_db)
    
    user = make_user()
    result = service.create(user)
    
    assert result is True
    mock_db.save.assert_called_once_with(user)
```

## Async Testing

```python
import pytest

@pytest.mark.asyncio
async def test_fetches_user():
    user = await user_service.find_by_id("123")
    assert user.name == "John"

@pytest.mark.asyncio
async def test_raises_when_not_found():
    with pytest.raises(UserNotFoundError):
        await user_service.find_by_id("missing")
```

## Parametrized Tests

```python
@pytest.mark.parametrize("input,expected", [
    ("test@example.com", True),
    ("invalid", False),
    ("", False),
    ("a@b.c", True),
])
def test_validates_email(input, expected):
    assert validate_email(input) == expected
```

## Coverage

### Configuration (pyproject.toml)
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --cov=src --cov-report=term-missing"

[tool.coverage.run]
source = ["src"]
omit = ["*/__init__.py", "*/types.py"]

[tool.coverage.report]
fail_under = 80
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
]
```

## TDD Cycle

1. **RED**: Write failing test
   ```python
   def test_rejects_empty_name(self):
       with pytest.raises(ValidationError, match="Name is required"):
           create_user(name="")
   ```

2. **GREEN**: Minimal implementation
   ```python
   def create_user(name: str) -> User:
       if not name:
           raise ValidationError("Name is required")
       # ...
   ```

3. **REFACTOR**: Clean up with tests green

## Timing-Sensitive Tests

Shell builtins (`echo`, `ls`, `true`) complete in under 1ms. Asserting `duration_ms > 0` against them is flaky because `int(duration * 1000)` rounds to 0.

**Use `python -c "pass"` (or any Python one-liner) instead** — Python interpreter startup guarantees measurable elapsed time (~5–50ms):

```python
# BAD — echo completes in <1ms, int(duration_ms) == 0 → flaky
commands_config = make_config("echo", ["echo", "hi"])
handler = _create_tool_handler("echo", commands_config, ...)
await handler()
assert log_entry["duration_ms"] > 0  # fails intermittently

# GOOD — Python startup guarantees >1ms
commands_config = make_config("py", ["python", "-c", "pass"])
handler = _create_tool_handler("py", commands_config, ...)
await handler()
assert log_entry["duration_ms"] > 0  # always passes
```

The same applies to any subprocess-timing assertion: use commands that include interpreter or linker startup rather than shell builtins.

## Filesystem / Permission Tests

Use `chmod 0o444` to simulate a non-writable path. Always restore permissions in a `finally` block so pytest `tmp_path` teardown succeeds:

```python
backup_dir.mkdir()
backup_dir.chmod(0o444)
try:
    with pytest.raises(SomeError):
        function_under_test(backup_dir)
finally:
    backup_dir.chmod(0o755)
```

Ensure production code wraps filesystem operations in a `try/except OSError` broad enough to catch `PermissionError`, `NotADirectoryError`, and related errors.

## Mocking Lazy Imports

`patch("module.Name", ...)` requires `Name` to be in `module`'s namespace **at the time `patch()` runs**. Names imported inside a function body are never added to the module's `__dict__`, so patching them raises `AttributeError`.

```python
# BAD — GoogleSearch imported inside function body, unpatchable
def fetch(params):
    from serpapi import GoogleSearch  # lazy import
    return GoogleSearch(params).get_dict()

# patching fails: AttributeError: module 'mymodule' has no attribute 'GoogleSearch'
with patch("mymodule.GoogleSearch", ...) as mock:
    ...

# GOOD — import at module level, patchable via module namespace
from serpapi import GoogleSearch  # module-level

def fetch(params):
    return GoogleSearch(params).get_dict()

with patch("mymodule.GoogleSearch", ...) as mock:
    ...
```

If moving the import to module level is not possible (e.g., optional dependency), patch the original module instead: `patch("serpapi.GoogleSearch", ...)`.

## Anti-Patterns

- ❌ Testing implementation details
- ❌ Mocking everything
- ❌ Shared mutable state between tests
- ❌ Tests that depend on execution order
- ❌ `@pytest.mark.skip` without issue reference
- ❌ Assertions without messages for complex conditions
