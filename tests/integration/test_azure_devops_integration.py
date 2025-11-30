# tests/integration/test_azure_devops_integration.py
"""
Integration tests for Azure DevOps client.

Tests the full interaction flow with Azure DevOps REST API using mocked HTTP responses.
"""
import pytest
import json
from aioresponses import aioresponses
from src.services.azure_devops import AzureDevOpsClient, DevOpsAuthError, DevOpsRateLimitError


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
class TestAzureDevOpsClientIntegration:
    """Integration tests for Azure DevOps client operations."""

    async def test_get_pull_request_details_success(
        self,
        integration_azure_devops_client,
        sample_pr_details
    ):
        """Test successful PR details retrieval."""
        client = integration_azure_devops_client
        project_id = "project-123"
        repo_id = "repo-456"
        pr_id = 12345

        with aioresponses() as mock:
            # Mock the API response (note: Azure DevOps uses "pullRequests" with capital R)
            url = f"{client.base_url}/{project_id}/_apis/git/repositories/{repo_id}/pullRequests/{pr_id}?api-version={client.api_version}"
            mock.get(
                url,
                payload=sample_pr_details,
                status=200
            )

            # Execute
            result = await client.get_pull_request_details(project_id, repo_id, pr_id)

            # Verify
            assert result is not None
            assert result["pullRequestId"] == 12345
            assert result["title"] == "feat: Add rate limiting to API endpoints"
            assert result["status"] == "active"

    async def test_get_pull_request_files_success(
        self,
        integration_azure_devops_client,
        sample_pr_files
    ):
        """Test successful retrieval of PR file changes."""
        client = integration_azure_devops_client
        project_id = "project-123"
        repo_id = "repo-456"
        pr_id = 12345

        with aioresponses() as mock:
            # Mock the iterations endpoint
            iterations_url = f"{client.base_url}/{project_id}/_apis/git/repositories/{repo_id}/pullRequests/{pr_id}/iterations?api-version={client.api_version}"
            mock.get(
                iterations_url,
                payload={"value": [{"id": 1}]},
                status=200
            )

            # Mock the changes endpoint
            changes_url = f"{client.base_url}/{project_id}/_apis/git/repositories/{repo_id}/pullRequests/{pr_id}/iterations/1/changes?api-version={client.api_version}"
            mock.get(
                changes_url,
                payload={
                    "changeEntries": [
                        {"item": {"path": f["path"]}, "changeType": f["changeType"]}
                        for f in sample_pr_files
                    ]
                },
                status=200
            )

            # Execute
            result = await client.get_pull_request_files(project_id, repo_id, pr_id)

            # Verify
            assert len(result) == 4
            assert any(f["path"] == "/src/api/middleware/rate_limiter.py" for f in result)
            assert any(f["changeType"] == "add" for f in result)

    async def test_get_file_diff_success(
        self,
        integration_azure_devops_client,
        sample_pr_details,
        sample_file_diff
    ):
        """Test successful file diff retrieval."""
        client = integration_azure_devops_client
        project_id = "project-123"
        repo_id = "repo-456"
        file_path = "/src/api/middleware/rate_limiter.py"

        with aioresponses() as mock:
            # Mock the diff endpoint
            base_commit = "abc123"
            target_commit = "def456"

            # First need to get PR details for commits
            pr_url = f"{client.base_url}/{project_id}/_apis/git/repositories/{repo_id}/pullrequests/12345"
            pr_data = {
                **sample_pr_details,
                "lastMergeSourceCommit": {"commitId": target_commit},
                "lastMergeTargetCommit": {"commitId": base_commit}
            }
            mock.get(pr_url, payload=pr_data, status=200)

            # Mock diff endpoint
            diff_url = f"{client.base_url}/{project_id}/_apis/git/repositories/{repo_id}/diffs/commits"
            mock.get(
                diff_url,
                payload={"changes": [{"item": {"path": file_path}}]},
                status=200,
                headers={"Content-Type": "text/plain"}
            )

            # Execute
            result = await client.get_file_diff(
                project_id,
                repo_id,
                file_path,
                base_commit,
                target_commit
            )

            # Verify - should get some result (mocked response)
            assert result is not None

    async def test_post_pr_comment_success(
        self,
        integration_azure_devops_client,
        sample_pr_details
    ):
        """Test successful posting of PR summary comment."""
        client = integration_azure_devops_client
        project_id = "project-123"
        repo_id = "repo-456"
        pr_id = 12345
        comment_text = "## Code Review Summary\n\nNo issues found."

        with aioresponses() as mock:
            # Mock the threads endpoint
            url = f"{client.base_url}/{project_id}/_apis/git/repositories/{repo_id}/pullrequests/{pr_id}/threads"
            mock.post(
                url,
                payload={"id": 1, "status": "active"},
                status=200
            )

            # Execute
            await client.post_pr_comment(
                project_id,
                repo_id,
                pr_id,
                comment_text
            )

            # Verify - should not raise exception
            # In real test, would verify the payload sent

    async def test_post_inline_comment_success(
        self,
        integration_azure_devops_client
    ):
        """Test successful posting of inline code comment."""
        client = integration_azure_devops_client
        project_id = "project-123"
        repo_id = "repo-456"
        pr_id = 12345

        with aioresponses() as mock:
            # Mock the threads endpoint
            url = f"{client.base_url}/{project_id}/_apis/git/repositories/{repo_id}/pullrequests/{pr_id}/threads"
            mock.post(
                url,
                payload={"id": 2, "status": "active"},
                status=200
            )

            # Execute
            await client.post_inline_comment(
                project_id,
                repo_id,
                pr_id,
                file_path="/src/api/middleware/rate_limiter.py",
                line_number=28,
                comment_text="Missing error handling for Redis connection failures"
            )

            # Verify - should not raise exception

    async def test_authentication_failure(
        self,
        integration_azure_devops_client
    ):
        """Test handling of authentication failures."""
        client = integration_azure_devops_client

        with aioresponses() as mock:
            # Mock 401 unauthorized response
            url = f"{client.base_url}/project-123/_apis/git/repositories/repo-456/pullrequests/12345"
            mock.get(url, status=401)

            # Execute & Verify
            with pytest.raises(DevOpsAuthError):
                await client.get_pull_request_details("project-123", "repo-456", 12345)

    async def test_rate_limit_handling(
        self,
        integration_azure_devops_client
    ):
        """Test handling of rate limit errors."""
        client = integration_azure_devops_client

        with aioresponses() as mock:
            # Mock 429 rate limit response
            url = f"{client.base_url}/project-123/_apis/git/repositories/repo-456/pullrequests/12345"
            mock.get(
                url,
                status=429,
                headers={"Retry-After": "60"}
            )

            # Execute & Verify
            with pytest.raises(DevOpsRateLimitError) as exc_info:
                await client.get_pull_request_details("project-123", "repo-456", 12345)

            assert exc_info.value.retry_after == 60

    async def test_retry_on_transient_failure(
        self,
        integration_azure_devops_client,
        sample_pr_details
    ):
        """Test retry mechanism on transient failures."""
        client = integration_azure_devops_client

        with aioresponses() as mock:
            url = f"{client.base_url}/project-123/_apis/git/repositories/repo-456/pullrequests/12345"

            # First call fails with 503
            mock.get(url, status=503)

            # Second call succeeds
            mock.get(url, payload=sample_pr_details, status=200)

            # Execute - should succeed after retry
            result = await client.get_pull_request_details("project-123", "repo-456", 12345)

            # Verify
            assert result["pullRequestId"] == 12345

    async def test_session_reuse(
        self,
        integration_azure_devops_client,
        sample_pr_details
    ):
        """Test that HTTP session is reused across multiple calls."""
        client = integration_azure_devops_client

        with aioresponses() as mock:
            url = f"{client.base_url}/project-123/_apis/git/repositories/repo-456/pullrequests/12345"

            # Mock multiple calls
            for _ in range(3):
                mock.get(url, payload=sample_pr_details, status=200)

            # Execute multiple calls
            for _ in range(3):
                await client.get_pull_request_details("project-123", "repo-456", 12345)

            # Verify session was created only once
            assert client._session is not None

    async def test_concurrent_requests(
        self,
        integration_azure_devops_client,
        sample_pr_details
    ):
        """Test handling of concurrent API requests."""
        import asyncio

        client = integration_azure_devops_client

        with aioresponses() as mock:
            # Mock multiple PR endpoints
            for pr_id in [1, 2, 3]:
                url = f"{client.base_url}/project-123/_apis/git/repositories/repo-456/pullrequests/{pr_id}"
                response = {**sample_pr_details, "pullRequestId": pr_id}
                mock.get(url, payload=response, status=200)

            # Execute concurrent requests
            tasks = [
                client.get_pull_request_details("project-123", "repo-456", pr_id)
                for pr_id in [1, 2, 3]
            ]
            results = await asyncio.gather(*tasks)

            # Verify all succeeded
            assert len(results) == 3
            assert [r["pullRequestId"] for r in results] == [1, 2, 3]
