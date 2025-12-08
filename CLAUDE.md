# CodeWarden - Claude Code Instructions

## Project Overview
CodeWarden is an AI-powered Pull Request reviewer for Azure DevOps. It's an Azure Functions application (Python 3.12+) that analyzes code changes and posts review comments.

## Critical Rules

### Version Management
- **Single source of truth**: `src/utils/config.py` contains `__version__`
- **Update version at TOP of file only**: Each file has a docstring with `Version: X.Y.Z - description`
- **NEVER put version numbers in the middle of code** - no inline `# v2.6.x:` comments
- When modifying a file, update all three:
  1. The `__version__` in `src/utils/config.py`
  2. The `Version:` line in the modified file's docstring
  3. Add an entry in `CHANGELOG.md` describing the change

### Constants
- **ALL magic numbers go in `src/utils/constants.py`**
- Never hardcode numbers like timeouts, limits, or thresholds in code
- Use `UPPER_SNAKE_CASE` for constant names
- Group constants by category with section headers
- Import specific constants: `from src.utils.constants import SPECIFIC_CONSTANT`

### Imports
```python
# Order: stdlib → third-party → internal (blank line between each)
import asyncio
from typing import Dict, List, Optional

import structlog
from pydantic import BaseModel

from src.models.pr_event import PREvent
from src.utils.constants import MAX_RETRY_ATTEMPTS
from src.utils.logging import get_logger
```
- Always use absolute imports from `src/`
- Never use `import *`
- Import specific items, not entire modules

## File Structure
```
src/
├── handlers/      # HTTP & Timer trigger orchestrators
├── models/        # Pydantic data models
├── prompts/       # AI prompt generation
├── services/      # Business logic & external APIs
└── utils/         # Config, logging, storage, constants
```

## Docstring Format
Every file must have a module docstring:
```python
# src/module_name.py
"""
Module Title

Description of what this module does.

Version: 2.6.33 - Brief change description
"""
```

Methods use Google-style docstrings:
```python
async def method_name(self, param: str) -> ReturnType:
    """
    Brief description.

    Args:
        param: Description of parameter

    Returns:
        Description of return value

    Raises:
        ValueError: When validation fails
    """
```

## Naming Conventions
| Type | Convention | Example |
|------|------------|---------|
| Classes | PascalCase | `PRWebhookHandler` |
| Functions/Methods | snake_case | `handle_pr_event` |
| Constants | UPPER_SNAKE_CASE | `MAX_RETRY_ATTEMPTS` |
| Private | Leading underscore | `_internal_method` |
| Variables | snake_case | `pr_id`, `file_path` |

## Type Hints
- **Required on all public methods**
- Use `Optional[T]` for nullable values
- Use `List`, `Dict`, `Tuple` from `typing`
- Pydantic models must have `Field()` with constraints

```python
from typing import Dict, List, Optional

async def process(self, items: List[str]) -> Optional[Dict[str, int]]:
```

## Error Handling
```python
# Specific exceptions first, generic last
try:
    result = await some_operation()
except ValueError as e:
    logger.warning("validation_failed", error=str(e))
except CircuitBreakerError:
    logger.error("service_unavailable")
    raise
except Exception as e:
    logger.exception("unexpected_error", error_type=type(e).__name__)
    raise
```

- Always log errors before re-raising
- Use custom exceptions for domain errors
- Best-effort cleanup in `finally` blocks

## Logging
```python
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Event names are snake_case, first positional argument
logger.info("pr_review_started", pr_id=123, files_count=5)
logger.warning("rate_limit_approaching", current=95, max=100)
logger.error("api_call_failed", error=str(e), status_code=500)
```

Standard fields: `pr_id`, `correlation_id`, `repository`, `error`, `error_type`, `duration_seconds`

## Pydantic Models
```python
from pydantic import BaseModel, Field, field_validator

class ReviewIssue(BaseModel):
    severity: IssueSeverity = Field(..., description="Issue severity")
    file_path: str = Field(..., max_length=2000)
    line_number: int = Field(ge=0, le=1000000)

    @field_validator('file_path')
    @classmethod
    def validate_path(cls, v: str) -> str:
        if '\x00' in v or '..' in v:
            raise ValueError("Invalid file path")
        return v

    class Config:
        use_enum_values = True
```

## Async Patterns
```python
# Use async context managers for resource management
async with PRWebhookHandler() as handler:
    result = await handler.handle_pr_event(pr_event)

# Concurrent operations with semaphore limiting
async with self._semaphore:
    result = await expensive_operation()
```

## Security Requirements
- **Validate all external input** with Pydantic validators
- **Check for null bytes** (`\x00`) in strings
- **Prevent path traversal** (reject `..` in paths)
- **Sanitize user text** before including in prompts
- **URL-encode** all query parameters and path segments
- **Never log secrets** - use `***` placeholders

## Testing
- Test files: `tests/test_*.py`
- Use `@pytest.mark.asyncio` for async tests
- Fixtures in `conftest.py`
- Markers: `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.slow`

## Code Quality
Run before committing:
```bash
black src/           # Format
ruff check src/      # Lint
mypy src/           # Type check
pytest              # Tests
```

## Common Patterns

### URL Encoding for Azure DevOps API
```python
from urllib.parse import quote

encoded_project = quote(project_name, safe='')
encoded_path = quote(file_path, safe='/')  # Preserve path separators
```

### Retry with Tenacity
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(MAX_RETRY_ATTEMPTS),
    wait=wait_exponential(min=RETRY_MIN_WAIT, max=RETRY_MAX_WAIT)
)
async def unreliable_operation():
```

### Caching
```python
from functools import lru_cache

@lru_cache(maxsize=1000)
def expensive_computation(key: str) -> Result:
```

## What NOT to Do
- Don't put version numbers in inline comments
- Don't hardcode magic numbers - use constants
- Don't use relative imports
- Don't catch bare `Exception` without logging
- Don't skip type hints on public methods
- Don't create new files for one-time code - edit existing
- Don't add features beyond what's requested
- Don't create documentation files unless explicitly asked
