# src/models/feedback.py
"""
Data models for feedback tracking and learning.

Represents developer feedback on AI suggestions for continuous improvement.
Includes few-shot learning support for adaptive AI reviews.

Version: 2.7.0 - Added FeedbackExample, LearningContext, RejectionPattern for few-shot learning
"""
from pydantic import BaseModel, Field, field_validator
from typing import Dict, List, Optional
from datetime import datetime, timezone
from enum import Enum
import json

from src.utils.constants import (
    MAX_EXAMPLE_CODE_SNIPPET_LENGTH,
    MAX_EXAMPLE_SUGGESTION_LENGTH,
    FEEDBACK_MIN_SAMPLES,
)


class FeedbackType(str, Enum):
    """Type of feedback received."""

    THREAD_RESOLVED = "thread_resolved"  # Developer marked thread as resolved
    THREAD_WONT_FIX = "thread_wont_fix"  # Developer marked as won't fix
    COMMENT_REACTION_UP = "reaction_thumbs_up"  # Thumbs up reaction
    COMMENT_REACTION_DOWN = "reaction_thumbs_down"  # Thumbs down reaction


class FeedbackEntity(BaseModel):
    """
    Represents a single piece of feedback from a developer.

    Stored in Azure Table Storage 'feedback' table.
    """

    # Table Storage keys
    PartitionKey: str = Field(..., max_length=1024, description="Repository ID")
    RowKey: str = Field(..., max_length=1024, description="Unique feedback ID (UUID)")

    # Feedback details
    pr_id: int = Field(..., gt=0, lt=2147483647, description="Pull request ID")
    thread_id: int = Field(..., gt=0, lt=2147483647, description="PR thread ID")
    comment_id: Optional[int] = Field(
        None, gt=0, lt=2147483647, description="Comment ID if applicable"
    )

    # Issue details
    issue_type: str = Field(..., max_length=200, description="Type of issue flagged")
    severity: str = Field(
        ..., max_length=50, description="Severity level (critical, high, medium, low)"
    )
    file_path: str = Field(
        ..., max_length=2000, description="File where issue was found"
    )

    # Feedback
    feedback_type: FeedbackType = Field(..., description="Type of feedback received")
    is_positive: bool = Field(..., description="True if feedback is positive")

    # Context
    repository: str = Field(..., max_length=500, description="Repository name")
    project: str = Field(..., max_length=500, description="Project name")
    author: str = Field(..., max_length=500, description="Feedback author")

    # Timestamps
    issue_created_at: datetime = Field(..., description="When issue was reported")
    feedback_received_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When feedback was received",
    )

    # Metadata
    ai_model: Optional[str] = Field(
        None, max_length=200, description="AI model that generated the issue"
    )
    review_id: Optional[str] = Field(
        None, max_length=200, description="Review ID for tracking"
    )

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str) -> str:
        """Validate severity is one of expected values."""
        valid_severities = ["critical", "high", "medium", "low", "info"]
        if v.lower() not in valid_severities:
            raise ValueError(f"severity must be one of {valid_severities}")
        return v.lower()

    def to_table_entity(self) -> dict:
        """
        Convert to dict for Azure Table Storage.

        Returns:
            Dictionary suitable for table storage
        """
        entity = self.model_dump()

        # Convert datetime to ISO format
        entity["issue_created_at"] = self.issue_created_at.isoformat()
        entity["feedback_received_at"] = self.feedback_received_at.isoformat()

        # Convert enum to string
        entity["feedback_type"] = self.feedback_type.value

        return entity

    @classmethod
    def from_table_entity(cls, entity: dict) -> "FeedbackEntity":
        """
        Create from Azure Table Storage entity.

        Args:
            entity: Dictionary from table storage

        Returns:
            FeedbackEntity instance

        Raises:
            ValueError: If entity data is invalid
        """
        if not isinstance(entity, dict):
            raise ValueError("entity must be a dictionary")

        # Parse datetime fields with timezone validation
        try:
            if isinstance(entity.get("issue_created_at"), str):
                dt = datetime.fromisoformat(entity["issue_created_at"])
                # Ensure timezone is set to UTC
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                entity["issue_created_at"] = dt
            if isinstance(entity.get("feedback_received_at"), str):
                dt = datetime.fromisoformat(entity["feedback_received_at"])
                # Ensure timezone is set to UTC
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                entity["feedback_received_at"] = dt
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Invalid datetime format in entity: {e}")

        return cls(**entity)

    class Config:
        use_enum_values = True


class ReviewHistoryEntity(BaseModel):
    """
    Represents historical PR review data for pattern analysis.

    Stored in Azure Table Storage 'reviewhistory' table.
    """

    # Table Storage keys
    PartitionKey: str = Field(..., max_length=1024, description="Repository ID")
    RowKey: str = Field(..., max_length=1024, description="Unique review ID")

    # PR details
    pr_id: int = Field(..., gt=0, lt=2147483647, description="Pull request ID")
    pr_title: str = Field(..., max_length=1000, description="PR title")
    pr_author: str = Field(..., max_length=500, description="PR author")

    # Review details
    recommendation: str = Field(
        ..., max_length=50, description="approve, request_changes, or comment"
    )
    issue_count: int = Field(
        default=0, ge=0, lt=100000, description="Total number of issues found"
    )
    critical_count: int = Field(
        default=0, ge=0, lt=100000, description="Number of critical issues"
    )
    high_count: int = Field(
        default=0, ge=0, lt=100000, description="Number of high severity issues"
    )
    medium_count: int = Field(
        default=0, ge=0, lt=100000, description="Number of medium severity issues"
    )
    low_count: int = Field(
        default=0, ge=0, lt=100000, description="Number of low severity issues"
    )

    # Issue types (serialized JSON array of types found)
    issue_types: str = Field(
        default="[]", max_length=10000, description="JSON array of issue types"
    )

    # Files reviewed (serialized JSON array)
    files_reviewed: str = Field(
        default="[]", max_length=50000, description="JSON array of file paths"
    )

    # Context
    repository: str = Field(..., max_length=500, description="Repository name")
    repository_id: Optional[str] = Field(
        None, max_length=100, description="Repository UUID for API calls"
    )
    project: str = Field(..., max_length=500, description="Project name")

    # Performance metrics
    tokens_used: int = Field(
        default=0, ge=0, lt=10000000, description="Tokens used for review"
    )
    estimated_cost: float = Field(
        default=0.0, ge=0, lt=10000.0, description="Estimated cost in USD"
    )
    duration_seconds: float = Field(
        default=0.0, ge=0, lt=86400.0, description="Review duration"
    )

    # Timestamps
    reviewed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When review was performed",
    )

    # Metadata
    ai_model: Optional[str] = Field(None, max_length=200, description="AI model used")
    review_strategy: Optional[str] = Field(
        None, max_length=50, description="single_pass, chunked, or hierarchical"
    )

    @field_validator("issue_types", "files_reviewed")
    @classmethod
    def validate_json_field(cls, v: str) -> str:
        """Validate that JSON fields contain valid JSON."""
        if not v:
            return "[]"
        try:
            parsed = json.loads(v)
            if not isinstance(parsed, list):
                raise ValueError("JSON field must contain an array")
            # Limit array size to prevent DoS
            if len(parsed) > 1000:
                raise ValueError("JSON array too large (max 1000 items)")
            return v
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")

    def to_table_entity(self) -> dict:
        """Convert to dict for Azure Table Storage."""
        entity = self.model_dump()
        entity["reviewed_at"] = self.reviewed_at.isoformat()
        return entity

    @classmethod
    def from_table_entity(cls, entity: dict) -> "ReviewHistoryEntity":
        """
        Create from Azure Table Storage entity.

        Args:
            entity: Dictionary from table storage

        Returns:
            ReviewHistoryEntity instance

        Raises:
            ValueError: If entity data is invalid
        """
        if not isinstance(entity, dict):
            raise ValueError("entity must be a dictionary")

        # Parse datetime field with timezone validation
        try:
            if isinstance(entity.get("reviewed_at"), str):
                dt = datetime.fromisoformat(entity["reviewed_at"])
                # Ensure timezone is set to UTC
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                entity["reviewed_at"] = dt
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Invalid datetime format in entity: {e}")

        return cls(**entity)

    @classmethod
    def from_review_result(
        cls,
        review_result,
        pr_data: dict,
        repository: str,
        project: str,
        repository_id: Optional[str] = None,
    ) -> "ReviewHistoryEntity":
        """
        Create from ReviewResult and PR data.

        Args:
            review_result: ReviewResult instance
            pr_data: PR metadata dict
            repository: Repository name
            project: Project name
            repository_id: Repository UUID for feedback collection

        Returns:
            ReviewHistoryEntity instance
        """
        import json
        from collections import Counter

        # Count issues by severity
        severity_counts = Counter(issue.severity for issue in review_result.issues)

        # Extract unique issue types
        issue_types = list(set(issue.issue_type for issue in review_result.issues))

        # Extract unique file paths
        files = list(set(issue.file_path for issue in review_result.issues))

        return cls(
            PartitionKey=repository,
            RowKey=review_result.review_id,
            pr_id=review_result.pr_id,
            pr_title=pr_data.get("title", "Unknown"),
            pr_author=pr_data.get("author", "Unknown"),
            recommendation=review_result.recommendation,
            issue_count=len(review_result.issues),
            critical_count=severity_counts.get("critical", 0),
            high_count=severity_counts.get("high", 0),
            medium_count=severity_counts.get("medium", 0),
            low_count=severity_counts.get("low", 0),
            issue_types=json.dumps(issue_types),
            files_reviewed=json.dumps(files),
            repository=repository,
            repository_id=repository_id,
            project=project,
            tokens_used=review_result.tokens_used,
            estimated_cost=review_result.estimated_cost,
            duration_seconds=review_result.duration_seconds,
            reviewed_at=review_result.reviewed_at,
        )

    class Config:
        use_enum_values = True


# =============================================================================
# FEW-SHOT LEARNING MODELS (v2.7.0)
# =============================================================================


class FeedbackExample(BaseModel):
    """
    Represents an accepted suggestion for few-shot learning.

    Used to provide AI with examples of suggestions that were
    successfully accepted by the team, improving future review quality.
    """

    issue_type: str = Field(..., max_length=200, description="Type of issue")
    code_snippet: str = Field(
        ...,
        max_length=MAX_EXAMPLE_CODE_SNIPPET_LENGTH,
        description="Code that was flagged",
    )
    suggestion: str = Field(
        ...,
        max_length=MAX_EXAMPLE_SUGGESTION_LENGTH,
        description="AI suggestion that was accepted",
    )
    file_path: str = Field(..., max_length=500, description="File context")
    severity: str = Field(..., max_length=50, description="Issue severity")
    acceptance_count: int = Field(
        default=1, ge=0, description="Times similar suggestions were accepted"
    )

    @field_validator("code_snippet", "suggestion")
    @classmethod
    def sanitize_content(cls, v: str) -> str:
        """Sanitize content to prevent prompt injection."""
        if not v:
            return ""
        # Remove null bytes
        v = v.replace("\x00", "")
        # Limit consecutive newlines
        while "\n\n\n" in v:
            v = v.replace("\n\n\n", "\n\n")
        return v.strip()


class RejectionPattern(BaseModel):
    """
    Represents a pattern of rejected suggestions.

    Identifies types of issues that the team consistently
    rejects, helping AI avoid similar false positives.
    """

    issue_type: str = Field(..., max_length=200, description="Type of issue rejected")
    reason: str = Field(
        ...,
        max_length=500,
        description="Why this pattern is rejected (inferred from context)",
    )
    rejection_count: int = Field(
        ..., ge=1, description="Number of times this pattern was rejected"
    )
    sample_context: Optional[str] = Field(
        None, max_length=200, description="Sample file/path context"
    )

    @field_validator("issue_type", "reason", "sample_context", mode="before")
    @classmethod
    def sanitize_content(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize content to prevent prompt injection."""
        if v is None:
            return None
        if not isinstance(v, str):
            v = str(v)
        # Remove null bytes
        v = v.replace("\x00", "")
        # Limit consecutive newlines
        while "\n\n\n" in v:
            v = v.replace("\n\n\n", "\n\n")
        return v.strip()


class LearningContext(BaseModel):
    """
    Enhanced learning context for adaptive AI reviews.

    Combines aggregate statistics with few-shot examples
    for prompt-based reinforcement learning.
    """

    # Repository identification
    repository: str = Field(..., max_length=500, description="Repository name")

    # Aggregate statistics (existing functionality)
    high_value_issue_types: List[str] = Field(
        default_factory=list,
        max_length=20,
        description="Issue types with high acceptance rate",
    )
    low_value_issue_types: List[str] = Field(
        default_factory=list,
        max_length=20,
        description="Issue types with low acceptance rate",
    )
    positive_feedback_rate: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Overall positive feedback rate"
    )
    total_feedback_count: int = Field(
        default=0, ge=0, description="Total feedback entries analyzed"
    )
    issue_type_stats: Dict[str, Dict[str, int]] = Field(
        default_factory=dict, description="Per-issue-type statistics"
    )

    # Few-shot examples (v2.7.0)
    examples: Dict[str, List[FeedbackExample]] = Field(
        default_factory=dict,
        description="Few-shot examples by issue type",
    )

    # Rejection patterns (v2.7.0)
    rejection_patterns: List[RejectionPattern] = Field(
        default_factory=list,
        max_length=10,
        description="Patterns the team consistently rejects",
    )

    # Metadata
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this context was generated",
    )
    days_analyzed: int = Field(
        default=30, ge=1, le=365, description="Number of days of feedback analyzed"
    )

    def has_sufficient_data(self) -> bool:
        """Check if context has enough data to be useful."""
        return self.total_feedback_count >= FEEDBACK_MIN_SAMPLES

    def has_examples(self) -> bool:
        """Check if context has few-shot examples."""
        return bool(self.examples)

    def has_rejection_patterns(self) -> bool:
        """Check if context has rejection patterns."""
        return bool(self.rejection_patterns)

    def to_legacy_dict(self) -> Dict:
        """
        Convert to legacy dictionary format for backward compatibility.

        Returns format expected by existing PromptFactory._build_learning_context_section()
        """
        return {
            "high_value_issue_types": self.high_value_issue_types,
            "low_value_issue_types": self.low_value_issue_types,
            "positive_feedback_rate": self.positive_feedback_rate,
            "total_feedback_count": self.total_feedback_count,
            "issue_type_stats": self.issue_type_stats,
        }

    class Config:
        use_enum_values = True
