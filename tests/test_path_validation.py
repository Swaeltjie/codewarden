# tests/test_path_validation.py
"""
Unit tests for file path validation and security.
"""
import pytest
from src.handlers.pr_webhook import PRWebhookHandler


class TestPathValidation:
    """Tests for file path validation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler = PRWebhookHandler()

    def test_safe_relative_path(self):
        """Test that safe relative paths are accepted."""
        safe_paths = [
            "main.tf",
            "modules/vpc/main.tf",
            "ansible/playbook.yml",
            "pipelines/azure-pipelines.yml"
        ]

        for path in safe_paths:
            assert self.handler._is_safe_path(path) is True

    def test_path_traversal_attempts(self):
        """Test that path traversal attempts are rejected."""
        malicious_paths = [
            "../../../etc/passwd",
            "..\\..\\windows\\system32",
            "./../../secrets.txt",
            "modules/../../etc/passwd"
        ]

        for path in malicious_paths:
            assert self.handler._is_safe_path(path) is False

    def test_absolute_paths_rejected(self):
        """Test that absolute paths are rejected."""
        absolute_paths = [
            "/etc/passwd",
            "/var/log/app.log",
            "c:\\windows\\system.ini",
            "\\\\network\\share\\file"
        ]

        for path in absolute_paths:
            assert self.handler._is_safe_path(path) is False

    def test_null_byte_injection(self):
        """Test that null byte injection is rejected."""
        path_with_null = "main.tf\x00.exe"

        assert self.handler._is_safe_path(path_with_null) is False

    def test_suspicious_system_paths(self):
        """Test that suspicious system paths are rejected."""
        suspicious = [
            "etc/passwd",
            "proc/self/environ",
            "windows/system.ini"
        ]

        for path in suspicious:
            assert self.handler._is_safe_path(path) is False
