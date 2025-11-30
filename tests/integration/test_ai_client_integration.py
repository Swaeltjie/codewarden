# tests/integration/test_ai_client_integration.py
"""
Integration tests for AI client.

Tests the full interaction flow with AI providers (OpenAI, Anthropic, Azure OpenAI)
using mocked API responses.
"""
import pytest
import json
from unittest.mock import AsyncMock, Mock, patch
from src.services.ai_client import AIClient


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
class TestAIClientIntegration:
    """Integration tests for AI client operations."""

    async def test_review_code_with_openai_success(
        self,
        integration_ai_client,
        sample_file_diff,
        sample_ai_review_response
    ):
        """Test successful code review with OpenAI."""
        client = integration_ai_client

        # Configure mock response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = json.dumps(sample_ai_review_response)
        mock_response.usage.prompt_tokens = 1500
        mock_response.usage.completion_tokens = 300

        client.client.chat.completions.create.return_value = mock_response

        # Execute
        result = await client.review_code(
            diff_content=sample_file_diff,
            pr_title="feat: Add rate limiting to API endpoints",
            pr_description="Implements rate limiting using Redis"
        )

        # Verify
        assert result is not None
        assert "issues" in result
        assert len(result["issues"]) == 3
        assert result["recommendation"] == "request_changes"
        assert result["security_score"] == 7
        assert result["best_practices_score"] == 6

        # Verify API was called
        client.client.chat.completions.create.assert_called_once()

    async def test_review_code_with_token_estimation(
        self,
        integration_ai_client,
        sample_file_diff
    ):
        """Test that token counting works correctly."""
        client = integration_ai_client

        # Setup mock response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = json.dumps({
            "issues": [],
            "recommendation": "approve",
            "summary": "Good",
            "security_score": 10,
            "best_practices_score": 10
        })
        mock_response.usage.prompt_tokens = 2000
        mock_response.usage.completion_tokens = 100

        client.client.chat.completions.create.return_value = mock_response

        # Execute
        result = await client.review_code(diff_content=sample_file_diff)

        # Verify token tracking
        assert result["_metadata"]["prompt_tokens"] == 2000
        assert result["_metadata"]["completion_tokens"] == 100
        assert result["_metadata"]["total_tokens"] == 2100

    async def test_review_code_validates_response_schema(
        self,
        integration_ai_client,
        sample_file_diff
    ):
        """Test that invalid AI responses are rejected."""
        client = integration_ai_client

        # Setup invalid response (missing required fields)
        invalid_response = {
            "issues": [
                {
                    "severity": "high",
                    # Missing 'message' field
                    "file_path": "/test.py",
                    "issue_type": "bug"
                }
            ],
            "recommendation": "approve"
            # Missing summary, security_score, best_practices_score
        }

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = json.dumps(invalid_response)
        mock_response.usage.prompt_tokens = 1000
        mock_response.usage.completion_tokens = 50

        client.client.chat.completions.create.return_value = mock_response

        # Execute & Verify
        with pytest.raises(Exception) as exc_info:
            await client.review_code(diff_content=sample_file_diff)

        assert "validation" in str(exc_info.value).lower() or "invalid" in str(exc_info.value).lower()

    async def test_review_code_handles_malformed_json(
        self,
        integration_ai_client,
        sample_file_diff
    ):
        """Test handling of malformed JSON responses from AI."""
        client = integration_ai_client

        # Setup malformed JSON response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "This is not valid JSON {invalid}"
        mock_response.usage.prompt_tokens = 1000
        mock_response.usage.completion_tokens = 50

        client.client.chat.completions.create.return_value = mock_response

        # Execute & Verify
        with pytest.raises(Exception) as exc_info:
            await client.review_code(diff_content=sample_file_diff)

        assert "json" in str(exc_info.value).lower() or "parse" in str(exc_info.value).lower()

    async def test_review_code_with_context_optimization(
        self,
        integration_ai_client
    ):
        """Test that large diffs are handled with context optimization."""
        client = integration_ai_client

        # Create a very large diff
        large_diff = "\n".join([
            f"+ Line {i} of new code content" for i in range(5000)
        ])

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = json.dumps({
            "issues": [],
            "recommendation": "approve",
            "summary": "Large diff reviewed",
            "security_score": 8,
            "best_practices_score": 8
        })
        mock_response.usage.prompt_tokens = 10000
        mock_response.usage.completion_tokens = 200

        client.client.chat.completions.create.return_value = mock_response

        # Execute - should handle large diff without crashing
        result = await client.review_code(diff_content=large_diff)

        # Verify
        assert result is not None
        assert result["recommendation"] == "approve"

    async def test_review_code_with_file_filters(
        self,
        integration_ai_client,
        sample_file_diff
    ):
        """Test code review with specific file type filtering."""
        client = integration_ai_client

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = json.dumps({
            "issues": [],
            "recommendation": "approve",
            "summary": "Python code looks good",
            "security_score": 9,
            "best_practices_score": 9
        })
        mock_response.usage.prompt_tokens = 1200
        mock_response.usage.completion_tokens = 150

        client.client.chat.completions.create.return_value = mock_response

        # Execute with file type context
        result = await client.review_code(
            diff_content=sample_file_diff,
            file_extensions=[".py"],
            pr_title="Python code changes"
        )

        # Verify
        assert result is not None

        # Verify the prompt includes Python-specific context
        call_args = client.client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        prompt_content = str(messages)
        assert "python" in prompt_content.lower() or ".py" in prompt_content.lower()

    async def test_concurrent_review_requests(
        self,
        integration_ai_client
    ):
        """Test handling of concurrent AI review requests."""
        import asyncio

        client = integration_ai_client

        # Setup mock responses
        def create_mock_response(review_id: int):
            mock = Mock()
            mock.choices = [Mock()]
            mock.choices[0].message.content = json.dumps({
                "issues": [],
                "recommendation": "approve",
                "summary": f"Review {review_id}",
                "security_score": 9,
                "best_practices_score": 9
            })
            mock.usage.prompt_tokens = 1000
            mock.usage.completion_tokens = 100
            return mock

        # Configure side effect to return different responses
        client.client.chat.completions.create.side_effect = [
            create_mock_response(i) for i in range(3)
        ]

        # Execute concurrent reviews
        diffs = [f"diff for review {i}" for i in range(3)]
        tasks = [client.review_code(diff_content=diff) for diff in diffs]
        results = await asyncio.gather(*tasks)

        # Verify all succeeded
        assert len(results) == 3
        assert all("summary" in r for r in results)

    async def test_cost_calculation_accuracy(
        self,
        integration_ai_client,
        sample_file_diff
    ):
        """Test accurate cost calculation for API usage."""
        client = integration_ai_client

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = json.dumps({
            "issues": [],
            "recommendation": "approve",
            "summary": "Good",
            "security_score": 9,
            "best_practices_score": 9
        })
        # Specific token counts for cost calculation
        mock_response.usage.prompt_tokens = 5000
        mock_response.usage.completion_tokens = 1000

        client.client.chat.completions.create.return_value = mock_response

        # Execute
        result = await client.review_code(diff_content=sample_file_diff)

        # Verify cost calculation
        assert "_metadata" in result
        assert "estimated_cost" in result["_metadata"]

        # Cost should be reasonable (not negative, not astronomical)
        cost = result["_metadata"]["estimated_cost"]
        assert 0 < cost < 1.0  # Should be a few cents, not dollars

    async def test_retry_on_rate_limit(
        self,
        integration_ai_client,
        sample_file_diff
    ):
        """Test retry mechanism on rate limit errors."""
        from openai import RateLimitError

        client = integration_ai_client

        # First call raises rate limit error
        rate_limit_error = RateLimitError(
            message="Rate limit exceeded",
            response=Mock(status_code=429),
            body=None
        )

        # Second call succeeds
        success_response = Mock()
        success_response.choices = [Mock()]
        success_response.choices[0].message.content = json.dumps({
            "issues": [],
            "recommendation": "approve",
            "summary": "Success after retry",
            "security_score": 9,
            "best_practices_score": 9
        })
        success_response.usage.prompt_tokens = 1000
        success_response.usage.completion_tokens = 100

        client.client.chat.completions.create.side_effect = [
            rate_limit_error,
            success_response
        ]

        # Execute - should succeed after retry
        result = await client.review_code(diff_content=sample_file_diff)

        # Verify
        assert result is not None
        assert result["summary"] == "Success after retry"

    async def test_timeout_handling(
        self,
        integration_ai_client,
        sample_file_diff
    ):
        """Test handling of API timeout errors."""
        import asyncio
        from openai import APITimeoutError

        client = integration_ai_client

        # Configure mock to raise timeout
        timeout_error = APITimeoutError(request=Mock())
        client.client.chat.completions.create.side_effect = timeout_error

        # Execute & Verify
        with pytest.raises(Exception) as exc_info:
            await client.review_code(diff_content=sample_file_diff)

        assert "timeout" in str(exc_info.value).lower()

    async def test_max_tokens_enforcement(
        self,
        integration_ai_client
    ):
        """Test that max tokens setting is respected."""
        client = integration_ai_client

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = json.dumps({
            "issues": [],
            "recommendation": "approve",
            "summary": "Good",
            "security_score": 9,
            "best_practices_score": 9
        })
        mock_response.usage.prompt_tokens = 1000
        mock_response.usage.completion_tokens = 100

        client.client.chat.completions.create.return_value = mock_response

        # Execute
        await client.review_code(diff_content="small diff", max_tokens=2048)

        # Verify max_tokens was passed to API
        call_args = client.client.chat.completions.create.call_args
        assert call_args.kwargs["max_tokens"] == 2048

    async def test_streaming_not_used(
        self,
        integration_ai_client,
        sample_file_diff
    ):
        """Test that streaming is disabled (we need complete responses)."""
        client = integration_ai_client

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = json.dumps({
            "issues": [],
            "recommendation": "approve",
            "summary": "Good",
            "security_score": 9,
            "best_practices_score": 9
        })
        mock_response.usage.prompt_tokens = 1000
        mock_response.usage.completion_tokens = 100

        client.client.chat.completions.create.return_value = mock_response

        # Execute
        await client.review_code(diff_content=sample_file_diff)

        # Verify streaming is disabled
        call_args = client.client.chat.completions.create.call_args
        assert call_args.kwargs.get("stream", False) is False
