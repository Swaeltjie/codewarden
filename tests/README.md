# CodeWarden Tests

This directory contains the test suite for the CodeWarden AI PR Reviewer.

## Running Tests

### Install test dependencies

```bash
pip install -r requirements-dev.txt
```

### Run all tests

```bash
pytest
```

### Run specific test file

```bash
pytest tests/test_diff_parser.py
```

### Run with coverage

```bash
pytest --cov=src --cov-report=html
```

### Run only unit tests

```bash
pytest -m unit
```

## Test Organization

- `conftest.py` - Shared fixtures and pytest configuration
- `test_*.py` - Test files organized by component
- Unit tests focus on individual functions and classes
- Integration tests test interactions between components

## Writing Tests

Follow these guidelines when adding new tests:

1. **Use descriptive test names** - Test names should clearly describe what is being tested
2. **Use fixtures** - Leverage pytest fixtures in `conftest.py` for common setup
3. **Test edge cases** - Include tests for error conditions and edge cases
4. **Keep tests isolated** - Each test should be independent and not rely on others
5. **Mock external dependencies** - Use mocks for Azure services, APIs, etc.

## Test Coverage Goals

- Aim for 80%+ code coverage
- All security-critical functions should have 100% coverage
- All public APIs should have comprehensive tests

## Current Test Coverage

Run `pytest --cov=src --cov-report=term-missing` to see current coverage.

Key areas to test:
- ✅ Webhook validation and security
- ✅ File path sanitization
- ✅ AI response validation
- ✅ Diff parsing
- ⏳ Azure DevOps API integration
- ⏳ AI client integration
- ⏳ End-to-end PR review workflow
