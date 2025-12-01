# tests/conftest.py
"""
Pytest configuration and fixtures for CodeWarden tests.
"""
import pytest
import os
from unittest.mock import Mock, AsyncMock
from datetime import datetime, timezone


@pytest.fixture
def mock_settings():
    """Mock application settings."""
    from unittest.mock import MagicMock

    settings = MagicMock()
    settings.ENVIRONMENT = "test"
    settings.LOG_LEVEL = "DEBUG"
    settings.AZURE_DEVOPS_ORG = "test-org"
    settings.OPENAI_MODEL = "gpt-4"
    settings.OPENAI_MAX_TOKENS = 4096
    settings.AZURE_AI_ENDPOINT = None

    return settings


@pytest.fixture
def mock_secret_manager():
    """Mock secret manager for testing."""
    manager = Mock()
    manager.get_secret.return_value = "test-secret-value"
    return manager


@pytest.fixture
def sample_pr_event():
    """Sample PR event data for testing."""
    return {
        "eventType": "git.pullrequest.created",
        "resource": {
            "pullRequestId": 123,
            "repository": {
                "id": "repo-id-123",
                "name": "test-repo",
                "project": {
                    "id": "project-id-123",
                    "name": "test-project"
                }
            },
            "title": "Test PR: Add new feature",
            "description": "This is a test pull request",
            "createdBy": {
                "displayName": "Test User",
                "uniqueName": "test@example.com"
            },
            "sourceRefName": "refs/heads/feature-branch",
            "targetRefName": "refs/heads/main"
        }
    }


@pytest.fixture
def sample_diff_content():
    """Sample unified diff content for testing."""
    # Hunk header: @@ -old_start,old_lines +new_start,new_lines @@
    # Context (space): 3, Removed (-): 1, Added (+): 5
    # Old = 3 context + 1 removed = 4 lines
    # New = 3 context + 5 added = 8 lines
    return """diff --git a/main.tf b/main.tf
--- a/main.tf
+++ b/main.tf
@@ -1,4 +1,8 @@
 resource "azurerm_resource_group" "example" {
   name     = "example-resources"
-  location = "West Europe"
+  location = "East US"
+
+  tags = {
+    environment = "production"
+  }
 }
"""


@pytest.fixture
def sample_ai_response():
    """Sample AI response for testing."""
    return {
        "issues": [
            {
                "severity": "medium",
                "description": "Consider using a variable for the location",
                "file_path": "/main.tf",
                "line_number": 3,
                "category": "best_practice"
            }
        ],
        "recommendation": "comment",
        "summary": "Overall the changes look good with minor suggestions",
        "security_score": 8,
        "best_practices_score": 7
    }


@pytest.fixture
async def mock_azure_devops_client():
    """Mock Azure DevOps client for testing."""
    from unittest.mock import AsyncMock

    client = AsyncMock()
    client.get_pull_request_details.return_value = {
        "title": "Test PR",
        "description": "Test description",
        "sourceRefName": "refs/heads/feature",
        "targetRefName": "refs/heads/main"
    }
    client.get_pull_request_files.return_value = []
    client.get_file_diff.return_value = ""

    return client


@pytest.fixture
async def mock_ai_client():
    """Mock AI client for testing."""
    from unittest.mock import AsyncMock

    client = AsyncMock()
    client.review_code.return_value = {
        "issues": [],
        "recommendation": "approve",
        "summary": "No issues found"
    }
    client.count_tokens.return_value = 100

    return client


# Set test environment variables
os.environ.setdefault('AZURE_STORAGE_CONNECTION_STRING', 'DefaultEndpointsProtocol=https;AccountName=test;AccountKey=test==;EndpointSuffix=core.windows.net')
os.environ.setdefault('KEYVAULT_URL', 'https://test-vault.vault.azure.net/')
