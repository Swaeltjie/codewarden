# Integration Tests

Comprehensive integration tests for CodeWarden's PR review workflow.

## Overview

These integration tests verify that components work correctly together, simulating real-world scenarios with mocked external dependencies (Azure DevOps API, OpenAI/Anthropic APIs).

## Test Structure

```
tests/integration/
├── conftest.py                          # Integration test fixtures and setup
├── test_azure_devops_integration.py     # Azure DevOps client integration tests
├── test_ai_client_integration.py        # AI client integration tests
├── test_webhook_handler_integration.py  # Webhook handler integration tests
└── test_e2e_pr_review.py               # End-to-end workflow tests
```

## Running Integration Tests

### Run all integration tests
```bash
pytest tests/integration/ -v
```

### Run specific test file
```bash
pytest tests/integration/test_azure_devops_integration.py -v
```

### Run with coverage
```bash
pytest tests/integration/ --cov=src --cov-report=html
```

### Run only integration tests (using markers)
```bash
pytest -m integration
```

### Run excluding slow tests
```bash
pytest tests/integration/ -m "not slow"
```

## Test Categories

### 1. Azure DevOps Client Integration (`test_azure_devops_integration.py`)

Tests Azure DevOps REST API interactions:
- ✅ PR details retrieval
- ✅ File list fetching
- ✅ Diff retrieval
- ✅ Comment posting (summary and inline)
- ✅ Authentication flows
- ✅ Rate limit handling
- ✅ Retry mechanisms
- ✅ Session reuse
- ✅ Concurrent requests

**Key Features:**
- Uses `aioresponses` to mock HTTP calls
- Tests actual client logic with realistic payloads
- Verifies error handling and retries

### 2. AI Client Integration (`test_ai_client_integration.py`)

Tests AI provider interactions:
- ✅ Code review generation (OpenAI, Anthropic, Azure OpenAI)
- ✅ Response validation and schema checking
- ✅ Token counting and cost estimation
- ✅ Context optimization for large diffs
- ✅ Malformed response handling
- ✅ Rate limit retry logic
- ✅ Timeout handling
- ✅ Concurrent review requests

**Key Features:**
- Mocks OpenAI/Anthropic API calls
- Tests actual response parsing and validation
- Verifies cost tracking accuracy

### 3. Webhook Handler Integration (`test_webhook_handler_integration.py`)

Tests webhook security and processing:
- ✅ Valid webhook processing
- ✅ Secret validation (timing-attack safe)
- ✅ Malformed JSON rejection
- ✅ Oversized payload protection (>1MB)
- ✅ Deep JSON nesting protection (DoS)
- ✅ Path traversal prevention
- ✅ Error handling without detail exposure
- ✅ Concurrent webhook handling
- ✅ Idempotency

**Key Features:**
- Tests security controls
- Verifies Azure Functions integration
- Tests error handling and monitoring

### 4. End-to-End Workflow (`test_e2e_pr_review.py`)

Tests complete PR review flow:
- ✅ Webhook → Fetch → Analyze → Comment (approve)
- ✅ Workflow with issues found (request changes)
- ✅ Large PR handling (>20 files)
- ✅ Azure DevOps API failure handling
- ✅ AI service failure handling
- ✅ Performance metrics (<30s target)

**Key Features:**
- Tests entire system integration
- Verifies all components work together
- Includes performance benchmarks

## Test Fixtures

Common fixtures available in `conftest.py`:

### HTTP Mocking
- `mock_aiohttp` - aioresponses instance for HTTP mocking

### Sample Data
- `sample_pr_details` - Realistic PR data from Azure DevOps
- `sample_pr_files` - List of changed files
- `sample_file_diff` - Unified diff content
- `sample_ai_review_response` - AI-generated review
- `sample_webhook_payload` - Complete webhook event

### Clients
- `integration_azure_devops_client` - Azure DevOps client with mocked auth
- `integration_ai_client` - AI client with mocked API calls
- `mock_secret_manager_integration` - Secret manager with test secrets
- `mock_settings_integration` - Application settings for testing

### Azure Functions
- `azure_function_context` - Mock Function context
- `azure_function_request` - Mock HTTP request

## Prerequisites

Install test dependencies:
```bash
pip install -r requirements-dev.txt
```

Key dependencies:
- `pytest` - Test framework
- `pytest-asyncio` - Async test support
- `pytest-cov` - Coverage reporting
- `pytest-mock` - Mocking utilities
- `aioresponses` - Mock aiohttp calls
- `respx` - Mock httpx calls (if needed)

## Environment Variables

Integration tests use mock secrets by default. No real credentials required.

If testing against real APIs (not recommended):
```bash
export AZURE_DEVOPS_ORG="your-org"
export OPENAI_API_KEY="sk-..."
# etc.
```

## Best Practices

### 1. Test Isolation
- Each test is independent
- Fixtures are function-scoped
- No shared state between tests

### 2. Realistic Scenarios
- Use actual data structures from Azure DevOps
- Test with realistic payloads
- Include edge cases

### 3. Performance
- Integration tests should complete quickly (<5s each)
- Mark slow tests with `@pytest.mark.slow`
- Use parallel test execution when possible

### 4. Error Handling
- Test both success and failure paths
- Verify error messages don't leak sensitive data
- Test retry mechanisms

## Continuous Integration

### GitHub Actions Example
```yaml
name: Integration Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt
      - name: Run integration tests
        run: pytest tests/integration/ -v --cov=src
```

## Troubleshooting

### Import Errors
Ensure you're running from the project root:
```bash
cd /path/to/CodeWarden
PYTHONPATH=. pytest tests/integration/
```

### Async Warnings
The `asyncio_mode = auto` setting in `pytest.ini` should handle this automatically.

### Mock Not Working
Verify the patch path matches the import path:
```python
# If code does: from src.services.azure_devops import AzureDevOpsClient
# Patch: 'src.services.azure_devops.DefaultAzureCredential'

# If code does: import openai
# Patch: 'openai.AsyncOpenAI'
```

### Flaky Tests
If tests fail intermittently:
1. Check for race conditions
2. Increase timeouts
3. Use `pytest-timeout` to catch hanging tests
4. Ensure proper cleanup in fixtures

## Coverage Goals

Target coverage for integration tests:
- **Azure DevOps Client**: >80%
- **AI Client**: >80%
- **Webhook Handler**: >90% (security critical)
- **End-to-End**: >70% (happy paths + critical errors)

Check coverage:
```bash
pytest tests/integration/ --cov=src --cov-report=term-missing
```

## Adding New Integration Tests

1. **Choose appropriate test file** based on component
2. **Use existing fixtures** from `conftest.py`
3. **Mark test properly**: `@pytest.mark.integration`
4. **Add slow marker if needed**: `@pytest.mark.slow`
5. **Document test purpose** in docstring
6. **Verify cleanup** - no leaked resources

Example:
```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_new_feature(
    integration_azure_devops_client,
    sample_pr_details
):
    """Test description explaining what's being verified."""
    # Arrange
    client = integration_azure_devops_client

    # Act
    result = await client.some_method()

    # Assert
    assert result is not None
```

## Security Testing

Integration tests include security scenarios:
- ✅ Webhook secret validation
- ✅ Path traversal prevention
- ✅ JSON bomb protection
- ✅ Payload size limits
- ✅ Input validation
- ✅ Error message sanitization

Run security tests:
```bash
pytest tests/integration/ -m security
```

## Related Documentation

- [Unit Tests](../README.md) - Unit test documentation
- [Testing Strategy](../../docs/testing-strategy.md) - Overall testing approach
- [CI/CD Pipeline](../../docs/ci-cd.md) - Automated testing setup
