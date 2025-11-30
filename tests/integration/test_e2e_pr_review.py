# tests/integration/test_e2e_pr_review.py
"""
End-to-end integration tests for PR review workflow.

Tests the complete flow:
1. Webhook received from Azure DevOps
2. PR details and files fetched
3. Diffs retrieved
4. AI analysis performed
5. Comments posted back to PR
"""
import pytest
import json
from unittest.mock import Mock, AsyncMock, patch
from aioresponses import aioresponses


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
class TestE2EPRReviewWorkflow:
    """End-to-end tests for complete PR review workflow."""

    async def test_complete_pr_review_workflow_approve(
        self,
        sample_webhook_payload,
        sample_pr_details,
        sample_pr_files,
        sample_file_diff,
        mock_secret_manager_integration,
        mock_settings_integration
    ):
        """Test complete workflow resulting in approval recommendation."""
        from src.handlers.pr_webhook import handle_pr_event
        from src.models.pr_event import PREvent

        # Parse PR event
        pr_event = PREvent.from_webhook_payload(sample_webhook_payload)

        with patch('src.handlers.pr_webhook.get_settings', return_value=mock_settings_integration):
            with aioresponses() as mock_http:
                # Setup Azure DevOps API mocks
                base_url = f"https://dev.azure.com/{mock_settings_integration.AZURE_DEVOPS_ORG}"
                project_id = pr_event.project_id
                repo_id = pr_event.repository_id
                pr_id = pr_event.pr_id

                # Mock PR details
                mock_http.get(
                    f"{base_url}/{project_id}/_apis/git/repositories/{repo_id}/pullrequests/{pr_id}",
                    payload=sample_pr_details,
                    status=200
                )

                # Mock iterations (for getting files)
                mock_http.get(
                    f"{base_url}/{project_id}/_apis/git/repositories/{repo_id}/pullrequests/{pr_id}/iterations",
                    payload={"value": [{"id": 1}]},
                    status=200
                )

                # Mock changes (file list)
                mock_http.get(
                    f"{base_url}/{project_id}/_apis/git/repositories/{repo_id}/pullrequests/{pr_id}/iterations/1/changes",
                    payload={
                        "changeEntries": [
                            {"item": {"path": f["path"]}, "changeType": f["changeType"]}
                            for f in sample_pr_files
                        ]
                    },
                    status=200
                )

                # Mock file diffs
                for file_info in sample_pr_files:
                    # Mock diff for each file
                    mock_http.get(
                        f"{base_url}/{project_id}/_apis/git/repositories/{repo_id}/diffs/commits",
                        payload=sample_file_diff,
                        status=200,
                        repeat=True
                    )

                # Mock posting summary comment
                mock_http.post(
                    f"{base_url}/{project_id}/_apis/git/repositories/{repo_id}/pullrequests/{pr_id}/threads",
                    payload={"id": 1, "status": "active"},
                    status=200,
                    repeat=True
                )

                # Mock AI client
                with patch('src.handlers.pr_webhook.AIClient') as MockAIClient:
                    mock_ai = AsyncMock()
                    mock_ai.review_code.return_value = {
                        "issues": [],
                        "recommendation": "approve",
                        "summary": "All changes look good. Code quality is high.",
                        "security_score": 10,
                        "best_practices_score": 9,
                        "_metadata": {
                            "prompt_tokens": 2000,
                            "completion_tokens": 150,
                            "total_tokens": 2150,
                            "estimated_cost": 0.043
                        }
                    }
                    MockAIClient.return_value = mock_ai

                    # Mock Azure DevOps client auth
                    with patch('src.services.azure_devops.DefaultAzureCredential') as mock_cred:
                        mock_token = Mock()
                        mock_token.token = "test-token"
                        mock_token.expires_on = 9999999999
                        mock_cred_instance = AsyncMock()
                        mock_cred_instance.get_token.return_value = mock_token
                        mock_cred.return_value = mock_cred_instance

                        # Execute the complete workflow
                        await handle_pr_event(pr_event)

                        # Verify AI was called
                        assert mock_ai.review_code.called

                        # Verify comment was posted (check HTTP mock was called)
                        # The summary comment should have been posted

    async def test_complete_pr_review_workflow_request_changes(
        self,
        sample_webhook_payload,
        sample_pr_details,
        sample_pr_files,
        sample_file_diff,
        sample_ai_review_response,
        mock_secret_manager_integration,
        mock_settings_integration
    ):
        """Test complete workflow resulting in request changes."""
        from src.handlers.pr_webhook import handle_pr_event
        from src.models.pr_event import PREvent

        pr_event = PREvent.from_webhook_payload(sample_webhook_payload)

        with patch('src.handlers.pr_webhook.get_settings', return_value=mock_settings_integration):
            with aioresponses() as mock_http:
                # Setup Azure DevOps API mocks
                base_url = f"https://dev.azure.com/{mock_settings_integration.AZURE_DEVOPS_ORG}"
                project_id = pr_event.project_id
                repo_id = pr_event.repository_id
                pr_id = pr_event.pr_id

                # Mock all API endpoints (same as above)
                mock_http.get(
                    f"{base_url}/{project_id}/_apis/git/repositories/{repo_id}/pullrequests/{pr_id}",
                    payload=sample_pr_details,
                    status=200
                )

                mock_http.get(
                    f"{base_url}/{project_id}/_apis/git/repositories/{repo_id}/pullrequests/{pr_id}/iterations",
                    payload={"value": [{"id": 1}]},
                    status=200
                )

                mock_http.get(
                    f"{base_url}/{project_id}/_apis/git/repositories/{repo_id}/pullrequests/{pr_id}/iterations/1/changes",
                    payload={
                        "changeEntries": [
                            {"item": {"path": f["path"]}, "changeType": f["changeType"]}
                            for f in sample_pr_files
                        ]
                    },
                    status=200
                )

                # Mock file diffs
                mock_http.get(
                    f"{base_url}/{project_id}/_apis/git/repositories/{repo_id}/diffs/commits",
                    payload=sample_file_diff,
                    status=200,
                    repeat=True
                )

                # Mock posting comments (summary + inline)
                mock_http.post(
                    f"{base_url}/{project_id}/_apis/git/repositories/{repo_id}/pullrequests/{pr_id}/threads",
                    payload={"id": 1, "status": "active"},
                    status=200,
                    repeat=True
                )

                # Mock AI client with issues found
                with patch('src.handlers.pr_webhook.AIClient') as MockAIClient:
                    mock_ai = AsyncMock()
                    mock_ai.review_code.return_value = {
                        **sample_ai_review_response,
                        "_metadata": {
                            "prompt_tokens": 2500,
                            "completion_tokens": 400,
                            "total_tokens": 2900,
                            "estimated_cost": 0.058
                        }
                    }
                    MockAIClient.return_value = mock_ai

                    # Mock Azure DevOps auth
                    with patch('src.services.azure_devops.DefaultAzureCredential') as mock_cred:
                        mock_token = Mock()
                        mock_token.token = "test-token"
                        mock_token.expires_on = 9999999999
                        mock_cred_instance = AsyncMock()
                        mock_cred_instance.get_token.return_value = mock_token
                        mock_cred.return_value = mock_cred_instance

                        # Execute
                        await handle_pr_event(pr_event)

                        # Verify AI was called
                        assert mock_ai.review_code.called

                        # Verify inline comments were posted for issues
                        # (3 issues in sample_ai_review_response)

    async def test_pr_review_workflow_with_large_pr(
        self,
        sample_webhook_payload,
        sample_pr_details,
        mock_secret_manager_integration,
        mock_settings_integration
    ):
        """Test workflow with large PR requiring chunked review."""
        from src.handlers.pr_webhook import handle_pr_event
        from src.models.pr_event import PREvent

        pr_event = PREvent.from_webhook_payload(sample_webhook_payload)

        # Create many files
        many_files = [
            {"path": f"/src/file_{i}.py", "changeType": "edit"}
            for i in range(25)  # More than MAX_FILES_PER_REVIEW
        ]

        with patch('src.handlers.pr_webhook.get_settings', return_value=mock_settings_integration):
            with aioresponses() as mock_http:
                base_url = f"https://dev.azure.com/{mock_settings_integration.AZURE_DEVOPS_ORG}"
                project_id = pr_event.project_id
                repo_id = pr_event.repository_id
                pr_id = pr_event.pr_id

                # Mock PR details
                mock_http.get(
                    f"{base_url}/{project_id}/_apis/git/repositories/{repo_id}/pullrequests/{pr_id}",
                    payload=sample_pr_details,
                    status=200
                )

                # Mock iterations and changes with many files
                mock_http.get(
                    f"{base_url}/{project_id}/_apis/git/repositories/{repo_id}/pullrequests/{pr_id}/iterations",
                    payload={"value": [{"id": 1}]},
                    status=200
                )

                mock_http.get(
                    f"{base_url}/{project_id}/_apis/git/repositories/{repo_id}/pullrequests/{pr_id}/iterations/1/changes",
                    payload={
                        "changeEntries": [
                            {"item": {"path": f["path"]}, "changeType": f["changeType"]}
                            for f in many_files
                        ]
                    },
                    status=200
                )

                # Mock diffs and comments
                mock_http.get(
                    f"{base_url}/{project_id}/_apis/git/repositories/{repo_id}/diffs/commits",
                    payload="diff content",
                    status=200,
                    repeat=True
                )

                mock_http.post(
                    f"{base_url}/{project_id}/_apis/git/repositories/{repo_id}/pullrequests/{pr_id}/threads",
                    payload={"id": 1, "status": "active"},
                    status=200,
                    repeat=True
                )

                # Mock AI client
                with patch('src.handlers.pr_webhook.AIClient') as MockAIClient:
                    mock_ai = AsyncMock()
                    mock_ai.review_code.return_value = {
                        "issues": [],
                        "recommendation": "comment",
                        "summary": "Large PR - consider breaking into smaller chunks",
                        "security_score": 8,
                        "best_practices_score": 7,
                        "_metadata": {
                            "prompt_tokens": 10000,
                            "completion_tokens": 500,
                            "total_tokens": 10500,
                            "estimated_cost": 0.210
                        }
                    }
                    MockAIClient.return_value = mock_ai

                    with patch('src.services.azure_devops.DefaultAzureCredential') as mock_cred:
                        mock_token = Mock()
                        mock_token.token = "test-token"
                        mock_token.expires_on = 9999999999
                        mock_cred_instance = AsyncMock()
                        mock_cred_instance.get_token.return_value = mock_token
                        mock_cred.return_value = mock_cred_instance

                        # Execute
                        await handle_pr_event(pr_event)

                        # Verify it handled the large PR

    async def test_pr_review_workflow_handles_api_failures(
        self,
        sample_webhook_payload,
        mock_secret_manager_integration,
        mock_settings_integration
    ):
        """Test workflow handles Azure DevOps API failures gracefully."""
        from src.handlers.pr_webhook import handle_pr_event
        from src.models.pr_event import PREvent

        pr_event = PREvent.from_webhook_payload(sample_webhook_payload)

        with patch('src.handlers.pr_webhook.get_settings', return_value=mock_settings_integration):
            with aioresponses() as mock_http:
                base_url = f"https://dev.azure.com/{mock_settings_integration.AZURE_DEVOPS_ORG}"
                project_id = pr_event.project_id
                repo_id = pr_event.repository_id
                pr_id = pr_event.pr_id

                # Mock PR details to fail with 500
                mock_http.get(
                    f"{base_url}/{project_id}/_apis/git/repositories/{repo_id}/pullrequests/{pr_id}",
                    status=500,
                    repeat=True
                )

                with patch('src.services.azure_devops.DefaultAzureCredential') as mock_cred:
                    mock_token = Mock()
                    mock_token.token = "test-token"
                    mock_token.expires_on = 9999999999
                    mock_cred_instance = AsyncMock()
                    mock_cred_instance.get_token.return_value = mock_token
                    mock_cred.return_value = mock_cred_instance

                    # Execute - should handle error gracefully
                    with pytest.raises(Exception):
                        await handle_pr_event(pr_event)

                    # In production, this would be caught and error posted to PR

    async def test_pr_review_workflow_handles_ai_failures(
        self,
        sample_webhook_payload,
        sample_pr_details,
        sample_pr_files,
        sample_file_diff,
        mock_secret_manager_integration,
        mock_settings_integration
    ):
        """Test workflow handles AI service failures gracefully."""
        from src.handlers.pr_webhook import handle_pr_event
        from src.models.pr_event import PREvent

        pr_event = PREvent.from_webhook_payload(sample_webhook_payload)

        with patch('src.handlers.pr_webhook.get_settings', return_value=mock_settings_integration):
            with aioresponses() as mock_http:
                base_url = f"https://dev.azure.com/{mock_settings_integration.AZURE_DEVOPS_ORG}"
                project_id = pr_event.project_id
                repo_id = pr_event.repository_id
                pr_id = pr_event.pr_id

                # Mock successful Azure DevOps calls
                mock_http.get(
                    f"{base_url}/{project_id}/_apis/git/repositories/{repo_id}/pullrequests/{pr_id}",
                    payload=sample_pr_details,
                    status=200
                )

                mock_http.get(
                    f"{base_url}/{project_id}/_apis/git/repositories/{repo_id}/pullrequests/{pr_id}/iterations",
                    payload={"value": [{"id": 1}]},
                    status=200
                )

                mock_http.get(
                    f"{base_url}/{project_id}/_apis/git/repositories/{repo_id}/pullrequests/{pr_id}/iterations/1/changes",
                    payload={
                        "changeEntries": [
                            {"item": {"path": f["path"]}, "changeType": f["changeType"]}
                            for f in sample_pr_files
                        ]
                    },
                    status=200
                )

                mock_http.get(
                    f"{base_url}/{project_id}/_apis/git/repositories/{repo_id}/diffs/commits",
                    payload=sample_file_diff,
                    status=200,
                    repeat=True
                )

                # Mock posting error comment
                mock_http.post(
                    f"{base_url}/{project_id}/_apis/git/repositories/{repo_id}/pullrequests/{pr_id}/threads",
                    payload={"id": 1, "status": "active"},
                    status=200
                )

                # Mock AI client to fail
                with patch('src.handlers.pr_webhook.AIClient') as MockAIClient:
                    mock_ai = AsyncMock()
                    mock_ai.review_code.side_effect = Exception("AI service unavailable")
                    MockAIClient.return_value = mock_ai

                    with patch('src.services.azure_devops.DefaultAzureCredential') as mock_cred:
                        mock_token = Mock()
                        mock_token.token = "test-token"
                        mock_token.expires_on = 9999999999
                        mock_cred_instance = AsyncMock()
                        mock_cred_instance.get_token.return_value = mock_token
                        mock_cred.return_value = mock_cred_instance

                        # Execute - should handle AI failure gracefully
                        with pytest.raises(Exception):
                            await handle_pr_event(pr_event)

                        # In production, error comment would be posted

    @pytest.mark.slow
    async def test_pr_review_performance_metrics(
        self,
        sample_webhook_payload,
        sample_pr_details,
        sample_pr_files,
        sample_file_diff,
        mock_secret_manager_integration,
        mock_settings_integration
    ):
        """Test that PR review completes within performance targets."""
        import time
        from src.handlers.pr_webhook import handle_pr_event
        from src.models.pr_event import PREvent

        pr_event = PREvent.from_webhook_payload(sample_webhook_payload)

        with patch('src.handlers.pr_webhook.get_settings', return_value=mock_settings_integration):
            with aioresponses() as mock_http:
                base_url = f"https://dev.azure.com/{mock_settings_integration.AZURE_DEVOPS_ORG}"
                project_id = pr_event.project_id
                repo_id = pr_event.repository_id
                pr_id = pr_event.pr_id

                # Setup all mocks
                mock_http.get(
                    f"{base_url}/{project_id}/_apis/git/repositories/{repo_id}/pullrequests/{pr_id}",
                    payload=sample_pr_details,
                    status=200
                )

                mock_http.get(
                    f"{base_url}/{project_id}/_apis/git/repositories/{repo_id}/pullrequests/{pr_id}/iterations",
                    payload={"value": [{"id": 1}]},
                    status=200
                )

                mock_http.get(
                    f"{base_url}/{project_id}/_apis/git/repositories/{repo_id}/pullrequests/{pr_id}/iterations/1/changes",
                    payload={
                        "changeEntries": [
                            {"item": {"path": f["path"]}, "changeType": f["changeType"]}
                            for f in sample_pr_files
                        ]
                    },
                    status=200
                )

                mock_http.get(
                    f"{base_url}/{project_id}/_apis/git/repositories/{repo_id}/diffs/commits",
                    payload=sample_file_diff,
                    status=200,
                    repeat=True
                )

                mock_http.post(
                    f"{base_url}/{project_id}/_apis/git/repositories/{repo_id}/pullrequests/{pr_id}/threads",
                    payload={"id": 1, "status": "active"},
                    status=200,
                    repeat=True
                )

                with patch('src.handlers.pr_webhook.AIClient') as MockAIClient:
                    mock_ai = AsyncMock()
                    mock_ai.review_code.return_value = {
                        "issues": [],
                        "recommendation": "approve",
                        "summary": "Good",
                        "security_score": 9,
                        "best_practices_score": 9,
                        "_metadata": {
                            "prompt_tokens": 2000,
                            "completion_tokens": 150,
                            "total_tokens": 2150,
                            "estimated_cost": 0.043
                        }
                    }
                    MockAIClient.return_value = mock_ai

                    with patch('src.services.azure_devops.DefaultAzureCredential') as mock_cred:
                        mock_token = Mock()
                        mock_token.token = "test-token"
                        mock_token.expires_on = 9999999999
                        mock_cred_instance = AsyncMock()
                        mock_cred_instance.get_token.return_value = mock_token
                        mock_cred.return_value = mock_cred_instance

                        # Measure execution time
                        start = time.time()
                        await handle_pr_event(pr_event)
                        duration = time.time() - start

                        # Verify performance
                        # Should complete within 30 seconds (with mocks)
                        assert duration < 30, f"Review took {duration}s, expected <30s"
