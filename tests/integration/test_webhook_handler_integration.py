# tests/integration/test_webhook_handler_integration.py
"""
Integration tests for webhook handler.

Tests the complete webhook processing flow including validation,
parsing, and response handling.
"""
import pytest
import json
from unittest.mock import Mock, AsyncMock, patch
from azure.functions import HttpRequest, HttpResponse


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
class TestWebhookHandlerIntegration:
    """Integration tests for PR webhook handler."""

    async def test_webhook_valid_pr_created_event(
        self,
        sample_webhook_payload,
        azure_function_context,
        mock_secret_manager_integration
    ):
        """Test handling of valid PR created webhook event."""
        from function_app import pr_webhook

        # Create HTTP request
        request = HttpRequest(
            method="POST",
            url="https://test.azurewebsites.net/api/pr-webhook",
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Secret": "integration-test-webhook-secret-key"
            },
            body=json.dumps(sample_webhook_payload).encode()
        )

        # Mock dependencies
        with patch('function_app.get_secret_manager', return_value=mock_secret_manager_integration):
            with patch('function_app.handle_pr_event') as mock_handler:
                mock_handler.return_value = AsyncMock()

                # Execute
                response: HttpResponse = await pr_webhook(request, azure_function_context)

                # Verify
                assert response.status_code == 202  # Accepted
                mock_handler.assert_called_once()

    async def test_webhook_invalid_secret_rejected(
        self,
        sample_webhook_payload,
        azure_function_context,
        mock_secret_manager_integration
    ):
        """Test that webhooks with invalid secrets are rejected."""
        from function_app import pr_webhook

        # Create request with wrong secret
        request = HttpRequest(
            method="POST",
            url="https://test.azurewebsites.net/api/pr-webhook",
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Secret": "wrong-secret"
            },
            body=json.dumps(sample_webhook_payload).encode()
        )

        # Mock secret manager
        with patch('function_app.get_secret_manager', return_value=mock_secret_manager_integration):
            # Execute
            response: HttpResponse = await pr_webhook(request, azure_function_context)

            # Verify - should be unauthorized
            assert response.status_code == 401

    async def test_webhook_missing_secret_rejected(
        self,
        sample_webhook_payload,
        azure_function_context,
        mock_secret_manager_integration
    ):
        """Test that webhooks without secret header are rejected."""
        from function_app import pr_webhook

        # Create request without secret header
        request = HttpRequest(
            method="POST",
            url="https://test.azurewebsites.net/api/pr-webhook",
            headers={"Content-Type": "application/json"},
            body=json.dumps(sample_webhook_payload).encode()
        )

        with patch('function_app.get_secret_manager', return_value=mock_secret_manager_integration):
            # Execute
            response: HttpResponse = await pr_webhook(request, azure_function_context)

            # Verify
            assert response.status_code == 401

    async def test_webhook_malformed_json_rejected(
        self,
        azure_function_context,
        mock_secret_manager_integration
    ):
        """Test that malformed JSON payloads are rejected."""
        from function_app import pr_webhook

        # Create request with invalid JSON
        request = HttpRequest(
            method="POST",
            url="https://test.azurewebsites.net/api/pr-webhook",
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Secret": "integration-test-webhook-secret-key"
            },
            body=b"{ this is not valid json }"
        )

        with patch('function_app.get_secret_manager', return_value=mock_secret_manager_integration):
            # Execute
            response: HttpResponse = await pr_webhook(request, azure_function_context)

            # Verify
            assert response.status_code == 400

    async def test_webhook_oversized_payload_rejected(
        self,
        azure_function_context,
        mock_secret_manager_integration
    ):
        """Test that oversized payloads are rejected."""
        from function_app import pr_webhook

        # Create request with very large payload (>1MB)
        large_payload = {
            "data": "x" * (2 * 1024 * 1024)  # 2MB of data
        }

        request = HttpRequest(
            method="POST",
            url="https://test.azurewebsites.net/api/pr-webhook",
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Secret": "integration-test-webhook-secret-key"
            },
            body=json.dumps(large_payload).encode()
        )

        with patch('function_app.get_secret_manager', return_value=mock_secret_manager_integration):
            # Execute
            response: HttpResponse = await pr_webhook(request, azure_function_context)

            # Verify - should reject oversized payload
            assert response.status_code == 413  # Payload too large

    async def test_webhook_deeply_nested_json_rejected(
        self,
        azure_function_context,
        mock_secret_manager_integration
    ):
        """Test that deeply nested JSON is rejected (DoS protection)."""
        from function_app import pr_webhook

        # Create deeply nested structure
        payload = {"level": {}}
        current = payload["level"]
        for i in range(20):  # Exceed max depth
            current["nested"] = {}
            current = current["nested"]

        request = HttpRequest(
            method="POST",
            url="https://test.azurewebsites.net/api/pr-webhook",
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Secret": "integration-test-webhook-secret-key"
            },
            body=json.dumps(payload).encode()
        )

        with patch('function_app.get_secret_manager', return_value=mock_secret_manager_integration):
            # Execute
            response: HttpResponse = await pr_webhook(request, azure_function_context)

            # Verify
            assert response.status_code == 400

    async def test_webhook_unsupported_event_type(
        self,
        sample_webhook_payload,
        azure_function_context,
        mock_secret_manager_integration
    ):
        """Test handling of unsupported event types."""
        from function_app import pr_webhook

        # Modify payload to unsupported event
        unsupported_payload = {
            **sample_webhook_payload,
            "eventType": "git.push"  # Not a PR event
        }

        request = HttpRequest(
            method="POST",
            url="https://test.azurewebsites.net/api/pr-webhook",
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Secret": "integration-test-webhook-secret-key"
            },
            body=json.dumps(unsupported_payload).encode()
        )

        with patch('function_app.get_secret_manager', return_value=mock_secret_manager_integration):
            # Execute
            response: HttpResponse = await pr_webhook(request, azure_function_context)

            # Verify - should accept but not process
            assert response.status_code in [200, 202]

    async def test_webhook_path_traversal_protection(
        self,
        sample_webhook_payload,
        azure_function_context,
        mock_secret_manager_integration
    ):
        """Test that path traversal attempts are blocked."""
        from function_app import pr_webhook

        # Modify payload with path traversal attempt
        malicious_payload = {
            **sample_webhook_payload,
            "resource": {
                **sample_webhook_payload["resource"],
                "repository": {
                    **sample_webhook_payload["resource"]["repository"],
                    "name": "../../etc/passwd"
                }
            }
        }

        request = HttpRequest(
            method="POST",
            url="https://test.azurewebsites.net/api/pr-webhook",
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Secret": "integration-test-webhook-secret-key"
            },
            body=json.dumps(malicious_payload).encode()
        )

        with patch('function_app.get_secret_manager', return_value=mock_secret_manager_integration):
            with patch('function_app.handle_pr_event') as mock_handler:
                # Execute
                response: HttpResponse = await pr_webhook(request, azure_function_context)

                # Verify - should reject or sanitize
                # The handler should not be called with malicious path
                if mock_handler.called:
                    call_args = mock_handler.call_args[0]
                    assert "../" not in str(call_args)

    async def test_webhook_error_handling_returns_500(
        self,
        sample_webhook_payload,
        azure_function_context,
        mock_secret_manager_integration
    ):
        """Test that internal errors return 500 without exposing details."""
        from function_app import pr_webhook

        request = HttpRequest(
            method="POST",
            url="https://test.azurewebsites.net/api/pr-webhook",
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Secret": "integration-test-webhook-secret-key"
            },
            body=json.dumps(sample_webhook_payload).encode()
        )

        with patch('function_app.get_secret_manager', return_value=mock_secret_manager_integration):
            with patch('function_app.handle_pr_event', side_effect=Exception("Internal error")):
                # Execute
                response: HttpResponse = await pr_webhook(request, azure_function_context)

                # Verify
                assert response.status_code == 500
                response_body = response.get_body().decode()

                # Should not expose internal error details
                assert "Internal error" not in response_body
                assert "error_id" in response_body.lower()

    async def test_webhook_concurrent_requests(
        self,
        sample_webhook_payload,
        azure_function_context,
        mock_secret_manager_integration
    ):
        """Test handling of concurrent webhook requests."""
        import asyncio
        from function_app import pr_webhook

        # Create multiple requests
        requests = []
        for i in range(5):
            payload = {
                **sample_webhook_payload,
                "resource": {
                    **sample_webhook_payload["resource"],
                    "pullRequestId": 100 + i
                }
            }
            request = HttpRequest(
                method="POST",
                url="https://test.azurewebsites.net/api/pr-webhook",
                headers={
                    "Content-Type": "application/json",
                    "X-Webhook-Secret": "integration-test-webhook-secret-key"
                },
                body=json.dumps(payload).encode()
            )
            requests.append(request)

        with patch('function_app.get_secret_manager', return_value=mock_secret_manager_integration):
            with patch('function_app.handle_pr_event') as mock_handler:
                mock_handler.return_value = AsyncMock()

                # Execute concurrently
                tasks = [
                    pr_webhook(req, azure_function_context)
                    for req in requests
                ]
                responses = await asyncio.gather(*tasks)

                # Verify all succeeded
                assert len(responses) == 5
                assert all(r.status_code == 202 for r in responses)

    async def test_webhook_idempotency(
        self,
        sample_webhook_payload,
        azure_function_context,
        mock_secret_manager_integration
    ):
        """Test that duplicate webhook deliveries are handled gracefully."""
        from function_app import pr_webhook

        request = HttpRequest(
            method="POST",
            url="https://test.azurewebsites.net/api/pr-webhook",
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Secret": "integration-test-webhook-secret-key"
            },
            body=json.dumps(sample_webhook_payload).encode()
        )

        with patch('function_app.get_secret_manager', return_value=mock_secret_manager_integration):
            with patch('function_app.handle_pr_event') as mock_handler:
                mock_handler.return_value = AsyncMock()

                # Execute same request twice
                response1 = await pr_webhook(request, azure_function_context)
                response2 = await pr_webhook(request, azure_function_context)

                # Verify both accepted (idempotent behavior)
                assert response1.status_code == 202
                assert response2.status_code == 202

    async def test_health_check_endpoint(
        self,
        azure_function_context
    ):
        """Test health check endpoint returns correctly."""
        from function_app import health_check

        request = HttpRequest(
            method="GET",
            url="https://test.azurewebsites.net/api/health",
            headers={}
        )

        # Execute
        response: HttpResponse = await health_check(request, azure_function_context)

        # Verify
        assert response.status_code == 200
        response_data = json.loads(response.get_body().decode())
        assert response_data["status"] == "healthy"
        assert "timestamp" in response_data
        assert "version" in response_data
