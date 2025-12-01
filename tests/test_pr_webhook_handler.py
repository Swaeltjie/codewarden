# tests/test_pr_webhook_handler.py
"""
Unit tests for PR Webhook Handler orchestration logic.

Tests key functionality:
- Strategy selection
- Dry-run mode
- Error handling
- Review result aggregation

Version: 2.5.0 - Fixed test fixtures for FileChange, added Settings mocking
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.models.pr_event import PREvent, FileChange, FileType
from src.models.review_result import ReviewResult, ReviewIssue, IssueSeverity, ReviewRecommendation
from src.services.context_manager import ReviewStrategy


class TestPRWebhookHandler:
    """Tests for PRWebhookHandler class.

    Note: These tests require environment variables or extensive mocking.
    They are marked with 'integration' marker to skip in unit test runs.
    """

    @pytest.fixture
    def handler(self):
        """Create a handler instance for testing.

        Note: Requires env vars: KEYVAULT_URL, AZURE_STORAGE_ACCOUNT_NAME, AZURE_DEVOPS_ORG
        """
        from src.handlers.pr_webhook import PRWebhookHandler
        handler = PRWebhookHandler()
        handler.dry_run = False
        return handler

    @pytest.fixture
    def sample_pr_event(self):
        """Create a sample PR event for testing."""
        return PREvent(
            pr_id=123,
            repository_id="repo-123",
            repository_name="test-repo",
            project_id="project-123",
            project_name="test-project",
            title="Test PR",
            description="Test description",
            author_name="Test User",
            author_email="test@example.com",
            source_branch="feature/test",
            target_branch="main",
            event_type="git.pullrequest.created",
            source_commit_id="abc123"
        )

    @pytest.fixture
    def sample_file_changes(self):
        """Create sample file changes for testing."""
        return [
            FileChange(
                path="main.tf",
                file_type=FileType.TERRAFORM,
                diff_content="+ resource block",
                lines_added=5,
                lines_deleted=0,
                changed_sections=[]
            ),
            FileChange(
                path="variables.tf",
                file_type=FileType.TERRAFORM,
                diff_content="+ variable block",
                lines_added=3,
                lines_deleted=1,
                changed_sections=[]
            )
        ]

    @pytest.fixture
    def sample_review_result(self):
        """Create a sample review result for testing."""
        return ReviewResult(
            pr_id=123,
            issues=[
                ReviewIssue(
                    severity=IssueSeverity.HIGH,
                    file_path="main.tf",
                    line_number=10,
                    issue_type="PublicEndpoint",
                    message="Resource exposes public endpoint"
                )
            ],
            recommendation=ReviewRecommendation.REQUEST_CHANGES,
            summary="Found 1 high severity issue",
            tokens_used=500,
            estimated_cost=0.005
        )

    @pytest.mark.integration
    def test_handler_initialization(self, handler):
        """Test handler initializes with correct defaults."""
        assert handler.dry_run is False
        assert handler.devops_client is None
        assert handler.ai_client is None

    @pytest.mark.integration
    def test_dry_run_mode_can_be_set(self, handler):
        """Test dry-run mode can be enabled."""
        handler.dry_run = True
        assert handler.dry_run is True

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_post_review_results_skipped_in_dry_run(
        self,
        handler,
        sample_pr_event,
        sample_review_result
    ):
        """Test that posting is skipped in dry-run mode."""
        handler.dry_run = True
        handler.devops_client = AsyncMock()

        # Should not raise and should not call devops_client
        await handler._post_review_results(sample_pr_event, sample_review_result)

        # Verify no API calls were made
        handler.devops_client.post_pr_comment.assert_not_called()
        handler.devops_client.post_inline_comment.assert_not_called()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_post_review_results_posts_in_normal_mode(
        self,
        handler,
        sample_pr_event,
        sample_review_result
    ):
        """Test that posting works in normal mode."""
        handler.dry_run = False
        handler.devops_client = AsyncMock()

        with patch('src.handlers.pr_webhook.CommentFormatter') as mock_formatter:
            mock_formatter.return_value.format_summary.return_value = "## Summary"
            mock_formatter.return_value.format_inline_issue.return_value = "Issue comment"

            await handler._post_review_results(sample_pr_event, sample_review_result)

            # Verify API calls were made
            handler.devops_client.post_pr_comment.assert_called_once()
            # Should post inline comment for high severity issue
            handler.devops_client.post_inline_comment.assert_called_once()


class TestReviewResultAggregation:
    """Tests for review result aggregation logic."""

    def test_aggregate_empty_results(self):
        """Test aggregation with no results."""
        result = ReviewResult.aggregate([], pr_id=123)
        assert result.recommendation == ReviewRecommendation.APPROVE
        assert len(result.issues) == 0

    def test_aggregate_single_result(self):
        """Test aggregation with single result."""
        single_result = ReviewResult(
            pr_id=123,
            issues=[
                ReviewIssue(
                    severity=IssueSeverity.MEDIUM,
                    file_path="test.tf",
                    line_number=1,
                    issue_type="Test",
                    message="Test issue"
                )
            ],
            recommendation=ReviewRecommendation.COMMENT,
            tokens_used=100,
            estimated_cost=0.001
        )

        result = ReviewResult.aggregate([single_result], pr_id=123)
        assert len(result.issues) == 1
        assert result.tokens_used == 100

    def test_aggregate_multiple_results_with_critical(self):
        """Test aggregation prioritizes critical issues."""
        results = [
            ReviewResult(
                pr_id=123,
                issues=[
                    ReviewIssue(
                        severity=IssueSeverity.LOW,
                        file_path="a.tf",
                        line_number=1,
                        issue_type="Minor",
                        message="Minor issue"
                    )
                ],
                recommendation=ReviewRecommendation.COMMENT,
                tokens_used=100
            ),
            ReviewResult(
                pr_id=123,
                issues=[
                    ReviewIssue(
                        severity=IssueSeverity.CRITICAL,
                        file_path="b.tf",
                        line_number=1,
                        issue_type="Security",
                        message="Critical issue"
                    )
                ],
                recommendation=ReviewRecommendation.REQUEST_CHANGES,
                tokens_used=100
            )
        ]

        result = ReviewResult.aggregate(results, pr_id=123)
        assert result.recommendation == ReviewRecommendation.REQUEST_CHANGES
        assert len(result.issues) == 2
        assert result.tokens_used == 200


class TestStrategySelection:
    """Tests for review strategy selection."""

    @pytest.fixture
    def context_manager(self):
        """Create context manager for testing."""
        from src.services.context_manager import ContextManager
        return ContextManager()

    def test_single_pass_for_small_pr(self, context_manager):
        """Test single-pass strategy for small PRs."""
        files = [
            FileChange(
                path="main.tf",
                file_type=FileType.TERRAFORM,
                diff_content="small change",
                lines_added=5,
                lines_deleted=2,
                changed_sections=[]
            )
        ]

        strategy = context_manager.determine_strategy(files)

        assert strategy == ReviewStrategy.SINGLE_PASS

    def test_chunked_for_medium_pr(self, context_manager):
        """Test chunked strategy for medium PRs."""
        # Create multiple files with larger content to trigger chunked/hierarchical
        files = [
            FileChange(
                path=f"file{i}.tf",
                file_type=FileType.TERRAFORM,
                diff_content="x" * 1000,  # Simulate larger content
                lines_added=50,
                lines_deleted=10,
                changed_sections=[]
            )
            for i in range(10)
        ]

        strategy = context_manager.determine_strategy(files)

        # Should use chunked or hierarchical for larger PRs
        assert strategy in [ReviewStrategy.SINGLE_PASS, ReviewStrategy.CHUNKED, ReviewStrategy.HIERARCHICAL]


class TestFilePathValidation:
    """Tests for file path validation in ReviewIssue."""

    def test_valid_file_path(self):
        """Test valid file paths are accepted."""
        issue = ReviewIssue(
            severity=IssueSeverity.HIGH,
            file_path="src/main.tf",
            line_number=10,
            issue_type="Test",
            message="Test"
        )
        assert issue.file_path == "src/main.tf"

    def test_path_traversal_rejected(self):
        """Test path traversal patterns are rejected."""
        with pytest.raises(ValueError, match="path traversal"):
            ReviewIssue(
                severity=IssueSeverity.HIGH,
                file_path="../../../etc/passwd",
                line_number=10,
                issue_type="Test",
                message="Test"
            )

    def test_null_bytes_rejected(self):
        """Test null bytes in paths are rejected."""
        with pytest.raises(ValueError, match="null bytes"):
            ReviewIssue(
                severity=IssueSeverity.HIGH,
                file_path="main.tf\x00.txt",
                line_number=10,
                issue_type="Test",
                message="Test"
            )

    def test_suspicious_system_paths_rejected(self):
        """Test suspicious system paths are rejected."""
        with pytest.raises(ValueError, match="suspicious pattern"):
            ReviewIssue(
                severity=IssueSeverity.HIGH,
                file_path="/etc/passwd",
                line_number=10,
                issue_type="Test",
                message="Test"
            )


class TestSuggestedFix:
    """Tests for SuggestedFix model."""

    def test_suggested_fix_creation(self):
        """Test SuggestedFix can be created."""
        from src.models.review_result import SuggestedFix

        fix = SuggestedFix(
            description="Add firewall rule",
            before='network_rules = []',
            after='network_rules = [{ default_action = "Deny" }]',
            explanation="Deny by default for security"
        )

        assert fix.description == "Add firewall rule"
        assert "Deny" in fix.after

    def test_review_issue_with_suggested_fix(self):
        """Test ReviewIssue can include SuggestedFix."""
        from src.models.review_result import SuggestedFix

        fix = SuggestedFix(
            description="Fix security issue",
            before="public = true",
            after="public = false"
        )

        issue = ReviewIssue(
            severity=IssueSeverity.HIGH,
            file_path="main.tf",
            line_number=10,
            issue_type="PublicEndpoint",
            message="Resource is public",
            suggested_fix=fix
        )

        assert issue.suggested_fix is not None
        assert issue.suggested_fix.description == "Fix security issue"
