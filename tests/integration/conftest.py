# tests/integration/conftest.py
"""
Integration test fixtures and configuration.

Provides realistic mock data and fixtures for testing component interactions.
"""
import pytest
import json
from typing import Dict, Any
from datetime import datetime, timezone
from aioresponses import aioresponses
from unittest.mock import AsyncMock, Mock, patch


@pytest.fixture
def mock_aiohttp():
    """Mock aiohttp responses for Azure DevOps API calls."""
    with aioresponses() as m:
        yield m


@pytest.fixture
def sample_pr_details() -> Dict[str, Any]:
    """Realistic pull request details from Azure DevOps."""
    return {
        "pullRequestId": 12345,
        "repository": {
            "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "name": "CodeWarden",
            "project": {
                "id": "project-123",
                "name": "Platform Engineering"
            }
        },
        "title": "feat: Add rate limiting to API endpoints",
        "description": "Implements rate limiting using Redis to prevent abuse",
        "sourceRefName": "refs/heads/feature/rate-limiting",
        "targetRefName": "refs/heads/main",
        "status": "active",
        "createdBy": {
            "displayName": "Jane Developer",
            "uniqueName": "jane@example.com",
            "id": "user-456"
        },
        "creationDate": "2025-11-30T10:00:00Z",
        "mergeStatus": "succeeded"
    }


@pytest.fixture
def sample_pr_files() -> list:
    """Sample list of changed files in a PR."""
    return [
        {
            "path": "/src/api/middleware/rate_limiter.py",
            "changeType": "add"
        },
        {
            "path": "/src/config/settings.py",
            "changeType": "edit"
        },
        {
            "path": "/tests/test_rate_limiter.py",
            "changeType": "add"
        },
        {
            "path": "/requirements.txt",
            "changeType": "edit"
        }
    ]


@pytest.fixture
def sample_file_diff() -> str:
    """Sample unified diff for a Python file."""
    return """diff --git a/src/api/middleware/rate_limiter.py b/src/api/middleware/rate_limiter.py
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/src/api/middleware/rate_limiter.py
@@ -0,0 +1,45 @@
+# src/api/middleware/rate_limiter.py
+\"\"\"
+Rate limiting middleware using Redis.
+\"\"\"
+import redis
+from fastapi import Request, HTTPException
+from datetime import datetime, timedelta
+
+
+class RateLimiter:
+    \"\"\"Rate limiter using sliding window algorithm.\"\"\"
+
+    def __init__(self, redis_client: redis.Redis, max_requests: int = 100):
+        self.redis = redis_client
+        self.max_requests = max_requests
+
+    async def check_rate_limit(self, client_id: str) -> bool:
+        \"\"\"
+        Check if client has exceeded rate limit.
+
+        Args:
+            client_id: Unique identifier for the client
+
+        Returns:
+            True if within limit, False if exceeded
+        \"\"\"
+        key = f"rate_limit:{client_id}"
+        current = self.redis.get(key)
+
+        if current is None:
+            # First request from this client
+            self.redis.setex(key, timedelta(hours=1), 1)
+            return True
+
+        count = int(current)
+        if count >= self.max_requests:
+            return False
+
+        # Increment counter
+        self.redis.incr(key)
+        return True
+
+
+async def rate_limit_middleware(request: Request):
+    \"\"\"FastAPI middleware for rate limiting.\"\"\"
+    # Implementation here
"""


@pytest.fixture
def sample_ai_review_response() -> Dict[str, Any]:
    """Sample AI-generated code review response."""
    return {
        "issues": [
            {
                "severity": "high",
                "message": "Missing error handling for Redis connection failures. If Redis is unavailable, the middleware will crash.",
                "file_path": "/src/api/middleware/rate_limiter.py",
                "line_number": 28,
                "issue_type": "error_handling"
            },
            {
                "severity": "medium",
                "message": "Type hints missing for return type of rate_limit_middleware function",
                "file_path": "/src/api/middleware/rate_limiter.py",
                "line_number": 44,
                "issue_type": "code_quality"
            },
            {
                "severity": "low",
                "message": "Consider using async Redis client (aioredis) for better async performance",
                "file_path": "/src/api/middleware/rate_limiter.py",
                "line_number": 12,
                "issue_type": "performance"
            }
        ],
        "recommendation": "request_changes",
        "summary": "The rate limiting implementation is a good start, but requires error handling improvements before merging. The main concern is the lack of Redis connection error handling which could cause service disruption.",
        "security_score": 7,
        "best_practices_score": 6
    }


@pytest.fixture
def sample_webhook_payload(sample_pr_details) -> Dict[str, Any]:
    """Sample webhook payload from Azure DevOps."""
    return {
        "subscriptionId": "sub-123",
        "notificationId": 1,
        "id": "webhook-event-789",
        "eventType": "git.pullrequest.created",
        "publisherId": "tfs",
        "message": {
            "text": "Pull request created",
            "html": "<p>Pull request created</p>",
            "markdown": "Pull request created"
        },
        "detailedMessage": {
            "text": "Jane Developer created pull request 12345"
        },
        "resource": sample_pr_details,
        "resourceVersion": "1.0",
        "resourceContainers": {
            "collection": {
                "id": "collection-id"
            },
            "account": {
                "id": "account-id"
            },
            "project": {
                "id": "project-123"
            }
        },
        "createdDate": "2025-11-30T10:00:00Z"
    }


@pytest.fixture
async def integration_azure_devops_client(mock_settings_integration):
    """
    Azure DevOps client configured for integration testing.

    Uses real client implementation but with mocked HTTP responses.
    """
    from src.services.azure_devops import AzureDevOpsClient

    # Mock the credential to avoid actual Azure AD calls
    with patch('src.services.azure_devops.DefaultAzureCredential') as mock_cred:
        with patch('src.services.azure_devops.get_settings', return_value=mock_settings_integration):
            mock_token = Mock()
            mock_token.token = "test-access-token-12345"
            mock_token.expires_on = 9999999999

            mock_cred_instance = AsyncMock()
            mock_cred_instance.get_token.return_value = mock_token
            mock_cred.return_value = mock_cred_instance

            client = AzureDevOpsClient()
            yield client

            # Cleanup
            if client._session:
                await client._session.close()


@pytest.fixture
async def integration_ai_client():
    """
    AI client configured for integration testing.

    Uses real client implementation but with mocked API responses.
    """
    from src.services.ai_client import AIClient

    # Mock the actual API calls but use real client logic
    with patch('openai.AsyncOpenAI') as mock_openai:
        mock_client = AsyncMock()
        mock_openai.return_value = mock_client

        client = AIClient()

        # Setup default mock response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = json.dumps({
            "issues": [],
            "recommendation": "approve",
            "summary": "Code looks good",
            "security_score": 9,
            "best_practices_score": 9
        })
        mock_response.usage.prompt_tokens = 1000
        mock_response.usage.completion_tokens = 200

        mock_client.chat.completions.create.return_value = mock_response

        yield client

        # Cleanup
        await client.close()


@pytest.fixture
def mock_secret_manager_integration():
    """Mock secret manager for integration tests with realistic secrets."""
    manager = Mock()
    manager.get_secret.side_effect = lambda key: {
        "WEBHOOK_SECRET": "integration-test-webhook-secret-key",
        "OPENAI_API_KEY": "sk-test-integration-key-12345",
        "ANTHROPIC_API_KEY": "sk-ant-test-integration-key",
        "AZURE_DEVOPS_PAT": None  # No PAT in integration tests
    }.get(key, "default-test-secret")
    return manager


@pytest.fixture
def mock_settings_integration():
    """Mock settings for integration tests."""
    from unittest.mock import MagicMock

    settings = MagicMock()
    settings.ENVIRONMENT = "integration-test"
    settings.LOG_LEVEL = "DEBUG"
    settings.AZURE_DEVOPS_ORG = "test-organization"
    settings.AZURE_STORAGE_ACCOUNT_NAME = "teststorageaccount"
    settings.OPENAI_MODEL = "gpt-4o"
    settings.OPENAI_MAX_TOKENS = 4096
    settings.AZURE_AI_ENDPOINT = None
    settings.AI_PROVIDER = "openai"
    settings.MAX_FILES_PER_REVIEW = 20
    settings.MAX_DIFF_SIZE_KB = 500
    settings.ENABLE_DATADOG = False

    return settings


@pytest.fixture
def azure_function_context():
    """Mock Azure Function context."""
    from unittest.mock import MagicMock

    context = MagicMock()
    context.invocation_id = "test-invocation-12345"
    context.function_name = "pr_webhook"
    context.function_directory = "/home/site/wwwroot"

    return context


@pytest.fixture
def azure_function_request():
    """Mock Azure Function HTTP request."""
    from unittest.mock import MagicMock

    request = MagicMock()
    request.method = "POST"
    request.url = "https://test-function.azurewebsites.net/api/pr-webhook"
    request.headers = {
        "Content-Type": "application/json",
        "X-Webhook-Secret": "integration-test-webhook-secret-key"
    }

    return request
