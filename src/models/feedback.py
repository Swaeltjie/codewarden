# src/models/feedback.py
"""
Data models for feedback tracking and learning.

Represents developer feedback on AI suggestions for continuous improvement.

Version: 2.0.0
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone
from enum import Enum


class FeedbackType(str, Enum):
    """Type of feedback received."""
    THREAD_RESOLVED = "thread_resolved"      # Developer marked thread as resolved
    THREAD_WONT_FIX = "thread_wont_fix"      # Developer marked as won't fix
    COMMENT_REACTION_UP = "reaction_thumbs_up"  # Thumbs up reaction
    COMMENT_REACTION_DOWN = "reaction_thumbs_down"  # Thumbs down reaction


class FeedbackEntity(BaseModel):
    """
    Represents a single piece of feedback from a developer.

    Stored in Azure Table Storage 'feedback' table.
    """

    # Table Storage keys
    PartitionKey: str = Field(..., description="Repository ID")
    RowKey: str = Field(..., description="Unique feedback ID (UUID)")

    # Feedback details
    pr_id: int = Field(..., description="Pull request ID")
    thread_id: int = Field(..., description="PR thread ID")
    comment_id: Optional[int] = Field(None, description="Comment ID if applicable")

    # Issue details
    issue_type: str = Field(..., description="Type of issue flagged")
    severity: str = Field(..., description="Severity level (critical, high, medium, low)")
    file_path: str = Field(..., description="File where issue was found")

    # Feedback
    feedback_type: FeedbackType = Field(..., description="Type of feedback received")
    is_positive: bool = Field(..., description="True if feedback is positive")

    # Context
    repository: str = Field(..., description="Repository name")
    project: str = Field(..., description="Project name")
    author: str = Field(..., description="Feedback author")

    # Timestamps
    issue_created_at: datetime = Field(..., description="When issue was reported")
    feedback_received_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When feedback was received"
    )

    # Metadata
    ai_model: Optional[str] = Field(None, description="AI model that generated the issue")
    review_id: Optional[str] = Field(None, description="Review ID for tracking")

    def to_table_entity(self) -> dict:
        """
        Convert to dict for Azure Table Storage.

        Returns:
            Dictionary suitable for table storage
        """
        entity = self.model_dump()

        # Convert datetime to ISO format
        entity['issue_created_at'] = self.issue_created_at.isoformat()
        entity['feedback_received_at'] = self.feedback_received_at.isoformat()

        # Convert enum to string
        entity['feedback_type'] = self.feedback_type.value

        return entity

    @classmethod
    def from_table_entity(cls, entity: dict) -> "FeedbackEntity":
        """
        Create from Azure Table Storage entity.

        Args:
            entity: Dictionary from table storage

        Returns:
            FeedbackEntity instance
        """
        # Parse datetime fields
        if isinstance(entity.get('issue_created_at'), str):
            entity['issue_created_at'] = datetime.fromisoformat(entity['issue_created_at'])
        if isinstance(entity.get('feedback_received_at'), str):
            entity['feedback_received_at'] = datetime.fromisoformat(entity['feedback_received_at'])

        return cls(**entity)

    class Config:
        use_enum_values = True


class ReviewHistoryEntity(BaseModel):
    """
    Represents historical PR review data for pattern analysis.

    Stored in Azure Table Storage 'reviewhistory' table.
    """

    # Table Storage keys
    PartitionKey: str = Field(..., description="Repository ID")
    RowKey: str = Field(..., description="Unique review ID")

    # PR details
    pr_id: int = Field(..., description="Pull request ID")
    pr_title: str = Field(..., description="PR title")
    pr_author: str = Field(..., description="PR author")

    # Review details
    recommendation: str = Field(..., description="approve, request_changes, or comment")
    issue_count: int = Field(default=0, description="Total number of issues found")
    critical_count: int = Field(default=0, description="Number of critical issues")
    high_count: int = Field(default=0, description="Number of high severity issues")
    medium_count: int = Field(default=0, description="Number of medium severity issues")
    low_count: int = Field(default=0, description="Number of low severity issues")

    # Issue types (serialized JSON array of types found)
    issue_types: str = Field(default="[]", description="JSON array of issue types")

    # Files reviewed (serialized JSON array)
    files_reviewed: str = Field(default="[]", description="JSON array of file paths")

    # Context
    repository: str = Field(..., description="Repository name")
    project: str = Field(..., description="Project name")

    # Performance metrics
    tokens_used: int = Field(default=0, description="Tokens used for review")
    estimated_cost: float = Field(default=0.0, description="Estimated cost in USD")
    duration_seconds: float = Field(default=0.0, description="Review duration")

    # Timestamps
    reviewed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When review was performed"
    )

    # Metadata
    ai_model: Optional[str] = Field(None, description="AI model used")
    review_strategy: Optional[str] = Field(None, description="single_pass, chunked, or hierarchical")

    def to_table_entity(self) -> dict:
        """Convert to dict for Azure Table Storage."""
        entity = self.model_dump()
        entity['reviewed_at'] = self.reviewed_at.isoformat()
        return entity

    @classmethod
    def from_table_entity(cls, entity: dict) -> "ReviewHistoryEntity":
        """Create from Azure Table Storage entity."""
        if isinstance(entity.get('reviewed_at'), str):
            entity['reviewed_at'] = datetime.fromisoformat(entity['reviewed_at'])
        return cls(**entity)

    @classmethod
    def from_review_result(
        cls,
        review_result,
        pr_data: dict,
        repository: str,
        project: str
    ) -> "ReviewHistoryEntity":
        """
        Create from ReviewResult and PR data.

        Args:
            review_result: ReviewResult instance
            pr_data: PR metadata dict
            repository: Repository name
            project: Project name

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
            pr_title=pr_data.get('title', 'Unknown'),
            pr_author=pr_data.get('author', 'Unknown'),
            recommendation=review_result.recommendation,
            issue_count=len(review_result.issues),
            critical_count=severity_counts.get('critical', 0),
            high_count=severity_counts.get('high', 0),
            medium_count=severity_counts.get('medium', 0),
            low_count=severity_counts.get('low', 0),
            issue_types=json.dumps(issue_types),
            files_reviewed=json.dumps(files),
            repository=repository,
            project=project,
            tokens_used=review_result.tokens_used,
            estimated_cost=review_result.estimated_cost,
            duration_seconds=review_result.duration_seconds,
            reviewed_at=review_result.reviewed_at
        )

    class Config:
        use_enum_values = True
