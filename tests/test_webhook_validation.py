# tests/test_webhook_validation.py
"""
Unit tests for webhook validation and security.
"""
import pytest
import json
from function_app import _validate_webhook_secret, _validate_json_depth


class TestWebhookValidation:
    """Tests for webhook validation functions."""

    def test_validate_webhook_secret_valid(self, monkeypatch, mock_secret_manager):
        """Test webhook secret validation with valid secret."""
        # Mock the secret manager
        def mock_get_secret_manager():
            return mock_secret_manager

        monkeypatch.setattr('function_app.get_secret_manager', mock_get_secret_manager)
        mock_secret_manager.get_secret.return_value = "correct-secret"

        result = _validate_webhook_secret("correct-secret")

        assert result is True

    def test_validate_webhook_secret_invalid(self, monkeypatch, mock_secret_manager):
        """Test webhook secret validation with invalid secret."""
        def mock_get_secret_manager():
            return mock_secret_manager

        monkeypatch.setattr('function_app.get_secret_manager', mock_get_secret_manager)
        mock_secret_manager.get_secret.return_value = "correct-secret"

        result = _validate_webhook_secret("wrong-secret")

        assert result is False

    def test_validate_webhook_secret_missing(self):
        """Test webhook secret validation with missing secret."""
        result = _validate_webhook_secret(None)

        assert result is False

    def test_validate_json_depth_acceptable(self):
        """Test JSON depth validation with acceptable depth."""
        data = {
            "level1": {
                "level2": {
                    "level3": "value"
                }
            }
        }

        result = _validate_json_depth(data, max_depth=10)

        assert result is True

    def test_validate_json_depth_too_deep(self):
        """Test JSON depth validation with excessive depth."""
        # Create deeply nested structure
        data = {"level": {}}
        current = data["level"]
        for i in range(15):
            current["nested"] = {}
            current = current["nested"]

        result = _validate_json_depth(data, max_depth=10)

        assert result is False

    def test_validate_json_depth_with_arrays(self):
        """Test JSON depth validation with nested arrays."""
        data = {
            "items": [
                {
                    "nested": [
                        {"value": "test"}
                    ]
                }
            ]
        }

        result = _validate_json_depth(data, max_depth=5)

        assert result is True
