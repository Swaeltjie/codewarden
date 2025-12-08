# Contributing to CodeWarden

Thank you for your interest in contributing to CodeWarden! This document provides guidelines and instructions for contributing.

## Getting Started

### Prerequisites

- Python 3.12+
- Azure CLI
- Azure Functions Core Tools v4
- Git

### Development Setup

```bash
# Clone the repository
git clone https://github.com/Swaeltjie/codewarden.git
cd codewarden

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Install pre-commit hooks
pre-commit install

# Login to Azure (for local development)
az login
```

### Running Locally

```bash
# Start the Azure Functions runtime
func start

# Run tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html
```

## Code Standards

### Style Guidelines

We use automated tools to enforce code style:

| Tool | Purpose | Command |
|------|---------|---------|
| **Black** | Code formatting | `black src/` |
| **Ruff** | Linting | `ruff check src/ --fix` |
| **mypy** | Type checking | `mypy src/` |
| **Bandit** | Security scanning | `bandit -r src/` |

Run all checks before committing:

```bash
pre-commit run --all-files
```

### Naming Conventions

| Type | Convention | Example |
|------|------------|---------|
| Classes | PascalCase | `PRWebhookHandler` |
| Functions/Methods | snake_case | `handle_pr_event` |
| Constants | UPPER_SNAKE_CASE | `MAX_RETRY_ATTEMPTS` |
| Private | Leading underscore | `_internal_method` |
| Variables | snake_case | `pr_id`, `file_path` |

### Type Hints

Type hints are required on all public methods:

```python
from typing import Dict, List, Optional

async def process_files(
    self,
    files: List[str],
    options: Optional[Dict[str, str]] = None
) -> bool:
    """Process a list of files."""
    ...
```

### Docstrings

Use Google-style docstrings:

```python
async def review_pr(self, pr_id: int, repo: str) -> ReviewResult:
    """
    Review a pull request and return findings.

    Args:
        pr_id: The pull request identifier
        repo: Repository name

    Returns:
        ReviewResult containing issues found

    Raises:
        ValueError: If pr_id is invalid
        APIError: If DevOps API call fails
    """
```

### Constants

All magic numbers go in `src/utils/constants.py`:

```python
# Good
from src.utils.constants import MAX_FILE_SIZE
if file_size > MAX_FILE_SIZE:
    ...

# Bad
if file_size > 1048576:  # What is this number?
    ...
```

### Imports

Order: stdlib, third-party, internal (blank line between each):

```python
import asyncio
from typing import Dict, List

import structlog
from pydantic import BaseModel

from src.models.pr_event import PREvent
from src.utils.constants import MAX_RETRY_ATTEMPTS
```

## Making Changes

### Branch Naming

- `feature/description` - New features
- `fix/description` - Bug fixes
- `docs/description` - Documentation changes
- `refactor/description` - Code refactoring

### Commit Messages

Write clear, concise commit messages:

```
Add webhook retry logic for transient failures

- Implement exponential backoff with jitter
- Add circuit breaker for repeated failures
- Log retry attempts with correlation ID
```

### Pull Requests

1. **Create a branch** from `main`
2. **Make your changes** following the code standards
3. **Write/update tests** for your changes
4. **Run all checks**: `pre-commit run --all-files`
5. **Submit a PR** with a clear description

PR description should include:
- What changes were made
- Why the changes were needed
- How to test the changes

## Testing

### Test Structure

```
tests/
├── unit/           # Unit tests (fast, isolated)
├── integration/    # Integration tests (may need Azure)
└── fixtures/       # Test data and mocks
```

### Writing Tests

```python
import pytest
from src.services.diff_parser import DiffParser

class TestDiffParser:
    """Tests for DiffParser service."""

    def test_parse_simple_diff(self):
        """Should parse a simple unified diff."""
        parser = DiffParser()
        result = parser.parse("@@ -1,3 +1,4 @@\n+new line")
        assert len(result.hunks) == 1

    @pytest.mark.asyncio
    async def test_async_operation(self):
        """Should handle async operations."""
        result = await some_async_function()
        assert result is not None
```

### Test Markers

- `@pytest.mark.unit` - Fast unit tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.slow` - Long-running tests

## Security

When contributing, please:

- Never commit secrets or credentials
- Validate all external input
- Use parameterized queries for storage operations
- Check for path traversal in file operations
- Run `bandit -r src/` before submitting

Report security vulnerabilities privately - do not open public issues.

## Questions?

- Open an issue for bugs or feature requests
- Check existing issues before creating new ones

Thank you for contributing!
