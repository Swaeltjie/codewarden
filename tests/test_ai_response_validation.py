# tests/test_ai_response_validation.py
"""
Unit tests for AI response validation.
"""
import pytest
from src.models.review_result import ReviewResult


class TestAIResponseValidation:
    """Tests for AI response validation."""

    def test_valid_ai_response(self, sample_ai_response):
        """Test parsing a valid AI response."""
        result = ReviewResult.from_ai_response(sample_ai_response, pr_id=123)

        assert result.pr_id == 123
        assert len(result.issues) == 1
        assert result.recommendation == "comment"
        assert result.summary == "Overall the changes look good with minor suggestions"

    def test_ai_response_missing_issues(self):
        """Test that missing issues field raises error."""
        invalid_response = {
            "recommendation": "approve",
            "summary": "Looks good"
        }

        with pytest.raises(ValueError, match="issues"):
            ReviewResult.from_ai_response(invalid_response, pr_id=123)

    def test_ai_response_missing_recommendation(self):
        """Test that missing recommendation field raises error."""
        invalid_response = {
            "issues": [],
            "summary": "Looks good"
        }

        with pytest.raises(ValueError, match="recommendation"):
            ReviewResult.from_ai_response(invalid_response, pr_id=123)

    def test_ai_response_invalid_issue_structure(self):
        """Test that invalid issue structure is handled."""
        invalid_response = {
            "issues": [
                {"severity": "high"}  # Missing required fields
            ],
            "recommendation": "approve",
            "summary": "Test"
        }

        # Should either raise ValueError or skip invalid issues
        try:
            result = ReviewResult.from_ai_response(invalid_response, pr_id=123)
            # If it doesn't raise, invalid issues should be filtered out
            assert len(result.issues) == 0
        except ValueError:
            # Or it should raise ValueError for invalid structure
            pass

    def test_ai_response_invalid_recommendation_value(self, sample_ai_response):
        """Test that invalid recommendation values are handled."""
        sample_ai_response["recommendation"] = "invalid_value"

        # Should either raise or default to safe value
        try:
            result = ReviewResult.from_ai_response(sample_ai_response, pr_id=123)
            # If it doesn't raise, should default to safe value
            assert result.recommendation in ["approve", "request_changes", "comment"]
        except ValueError:
            pass
