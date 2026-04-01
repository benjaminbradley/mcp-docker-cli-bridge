# Python Coding Conventions

## Naming

### Variables & Functions
- snake_case: `user_name`, `calculate_total`
- Descriptive: `is_authenticated` not `flag`
- Booleans: prefix with is_/has_/can_/should_

### Classes
- PascalCase: `UserProfile`, `ApiClient`
- Exception suffix: `ValidationError`, `NotFoundError`

### Constants
- SCREAMING_SNAKE_CASE: `MAX_RETRIES`, `DEFAULT_TIMEOUT`

### Private/Internal
- Single underscore prefix: `_internal_method`
- Double underscore for name mangling (rare): `__private`

### Files
- snake_case: `user_profile.py`, `api_client.py`
- Test files: `test_user_profile.py`

## Code Organization

### Imports
Order (separated by blank lines):
1. Standard library
2. Third-party packages
3. Local imports

```python
import os
from pathlib import Path

import requests
from pydantic import BaseModel

from .models import User
from .services import UserService
```

Use `isort` to maintain order automatically.

### File Structure
```python
"""Module docstring."""

# Imports

# Constants

# Type definitions / Protocols

# Classes

# Functions

# Main / CLI (if applicable)
if __name__ == "__main__":
    main()
```

## Type Hints

### Always Use Type Hints
```python
def create_user(name: str, email: str, age: int | None = None) -> User:
    ...

def process_items(items: list[Item]) -> dict[str, int]:
    ...
```

### Use Modern Syntax (3.10+)
```python
# Good (3.10+)
def func(x: int | None) -> list[str]:
    ...

# Avoid (old style)
from typing import Optional, List
def func(x: Optional[int]) -> List[str]:
    ...
```

### Complex Types
```python
from typing import TypeAlias, Callable

UserId: TypeAlias = str
Handler: TypeAlias = Callable[[Request], Response]
```

## Error Handling

### Use Specific Exceptions
```python
class UserNotFoundError(Exception):
    def __init__(self, user_id: str):
        self.user_id = user_id
        super().__init__(f"User not found: {user_id}")

# Usage
raise UserNotFoundError(user_id)
```

### Handle Exceptions Explicitly
```python
try:
    user = get_user(user_id)
except UserNotFoundError:
    return None
except DatabaseError as e:
    logger.error(f"Database error: {e}")
    raise
```

### Don't Catch Everything
```python
# Bad
try:
    do_something()
except:  # Catches everything including KeyboardInterrupt
    pass

# Good
try:
    do_something()
except ValueError as e:
    handle_error(e)
```

## Documentation

### Docstrings (Google Style)
```python
def calculate_total(items: list[Item], tax_rate: float = 0.0) -> float:
    """Calculate the total price including tax.
    
    Args:
        items: List of items to sum.
        tax_rate: Tax rate as decimal (e.g., 0.08 for 8%).
    
    Returns:
        Total price with tax applied.
    
    Raises:
        ValueError: If tax_rate is negative.
    """
    ...
```

### Class Docstrings
```python
class UserService:
    """Service for user management operations.
    
    Handles user creation, updates, and queries against
    the user database.
    
    Attributes:
        db: Database connection instance.
        cache: Optional cache for user lookups.
    """
```

## Formatting

- 4 spaces indentation
- Max line length: 88 characters (Black default)
- Use Black formatter
- Use isort for imports

## Patterns

### Early Returns
```python
def process_user(user: User | None) -> Result:
    if user is None:
        return Result.empty()
    if not user.is_active:
        return Result.inactive()
    # Main logic here
```

### Context Managers
```python
# For resource management
with open(path) as f:
    data = f.read()

# Custom context manager
@contextmanager
def timer(name: str):
    start = time.time()
    yield
    print(f"{name}: {time.time() - start:.2f}s")
```

### Dataclasses / Pydantic
```python
from dataclasses import dataclass

@dataclass(frozen=True)  # Immutable
class User:
    id: str
    name: str
    email: str
```

### String Normalization for Fuzzy Matching

When normalizing strings for deduplication or fuzzy comparison, replace non-word characters with a **space**, not an empty string. Removing them merges adjacent words:

```python
# BAD — "Senior-Engineer" → "SeniorEngineer" (merged, won't match "Senior Engineer")
re.sub(r"[^\w\s]", "", text)

# GOOD — "Senior-Engineer" → "Senior Engineer" (split preserved)
re.sub(r"[^\w\s]", " ", text)
```

Full normalization pattern:
```python
def normalize_for_dedup(text: str) -> str:
    cleaned = re.sub(r"[^\w\s]", " ", text).lower()
    return " ".join(sorted(cleaned.split()))  # sorted for order-independence
```

## Anti-Patterns

- ❌ Mutable default arguments: `def f(items=[])`
- ❌ Bare `except:` clauses
- ❌ Star imports: `from module import *`
- ❌ Global variables for state
- ❌ Deep nesting (max 3 levels)
- ❌ Single-letter variables (except `i`, `j` in loops)
