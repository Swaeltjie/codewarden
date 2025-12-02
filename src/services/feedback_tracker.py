# src/services/feedback_tracker.py
"""
Feedback Tracker

Tracks developer feedback on AI suggestions to improve over time.

Version: 2.5.5 - Fixed datetime parsing vulnerability
"""
import structlog
import uuid
import json
from typing import Dict, List, Optional
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict

from src.utils.table_storage import (
    get_table_client,
    ensure_table_exists,
    sanitize_odata_value,
    query_entities_paginated
)
from src.models.feedback import FeedbackEntity, FeedbackType
from src.services.azure_devops import AzureDevOpsClient
from src.utils.config import get_settings
from src.utils.constants import (
    FEEDBACK_TABLE_NAME,
    FEEDBACK_MIN_SAMPLES,
    FEEDBACK_HIGH_VALUE_THRESHOLD,
    FEEDBACK_LOW_VALUE_THRESHOLD,
    PATTERN_ANALYSIS_DAYS,
)

logger = structlog.get_logger(__name__)


class FeedbackTracker:
    """
    Tracks and analyzes developer feedback on AI suggestions.

    Features:
    - Monitors PR thread reactions (thumbs up/down)
    - Tracks resolved vs won't fix status
    - Learns which issue types are valuable
    - Adjusts review focus based on team preferences
    """

    def __init__(self):
        """Initialize feedback tracker."""
        self.settings = get_settings()
        self.devops_client = None
        logger.info("feedback_tracker_initialized")

    async def _get_devops_client(self) -> AzureDevOpsClient:
        """Get or create Azure DevOps client."""
        if self.devops_client is None:
            self.devops_client = AzureDevOpsClient()
        return self.devops_client

    async def close(self):
        """Close resources."""
        if self.devops_client:
            await self.devops_client.close()
            self.devops_client = None
        logger.debug("feedback_tracker_closed")

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - cleanup resources."""
        await self.close()
        return False

    async def collect_recent_feedback(self, hours: int = 24) -> int:
        """
        Collect feedback from PR threads in the last N hours.

        Queries Azure DevOps for:
        - Thread status changes (active → resolved)
        - Comment reactions (thumbs up/down)
        - Won't fix markers

        Args:
            hours: How many hours back to check

        Returns:
            Number of feedback entries collected
        """
        logger.info("feedback_collection_started", hours=hours)

        ensure_table_exists('feedback')
        table_client = get_table_client('feedback')

        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        feedback_collected = 0

        try:
            # Get recent reviews from history to find relevant PRs
            history_table = get_table_client('reviewhistory')

            # Query reviews from the last N hours
            # Note: Table Storage query with time filter
            query_filter = f"reviewed_at ge datetime'{cutoff_time.isoformat()}'"

            # Use pagination to avoid loading all reviews into memory
            recent_reviews = []
            for review in query_entities_paginated(history_table, query_filter=query_filter, page_size=100):
                recent_reviews.append(review)

            logger.info(
                "recent_reviews_found",
                count=len(recent_reviews),
                hours=hours
            )

            # For each recent review, check for feedback
            for review in recent_reviews:
                try:
                    feedback_count = await self._collect_pr_feedback(
                        review,
                        table_client
                    )
                    feedback_collected += feedback_count

                except Exception as e:
                    logger.warning(
                        "pr_feedback_collection_failed",
                        pr_id=review.get('pr_id'),
                        repository=review.get('repository'),
                        error=str(e)
                    )
                    continue

            logger.info(
                "feedback_collection_completed",
                feedback_entries=feedback_collected,
                reviews_checked=len(recent_reviews)
            )

            return feedback_collected

        except Exception as e:
            logger.exception(
                "feedback_collection_error",
                hours=hours,
                error=str(e),
                error_type=type(e).__name__
            )
            raise

    async def _collect_pr_feedback(
        self,
        review: dict,
        table_client
    ) -> int:
        """
        Collect feedback for a specific PR review.

        Args:
            review: Review history entity
            table_client: Table client for storing feedback

        Returns:
            Number of feedback items collected for this PR
        """
        devops = await self._get_devops_client()

        pr_id = review.get('pr_id')
        repository = review.get('repository')
        project = review.get('project')

        if not all([pr_id, repository, project]):
            logger.warning("missing_pr_metadata", review_id=review.get('RowKey'))
            return 0

        feedback_count = 0

        try:
            # Get PR threads/comments
            # Note: This is a simplified version - Azure DevOps API would need repository_id
            # For production, you'd need to store repository_id in review history
            repository_id = review.get('PartitionKey')  # Assuming PartitionKey is repo ID

            threads = await devops._get_pr_threads(project, repository_id, pr_id)

            # Parse issue types from review
            issue_types = json.loads(review.get('issue_types', '[]'))

            # Process each thread for feedback
            for thread in threads:
                feedback = await self._process_thread_feedback(
                    thread=thread,
                    pr_id=pr_id,
                    repository=repository,
                    project=project,
                    review_id=review.get('RowKey'),
                    issue_types=issue_types
                )

                if feedback:
                    # Store feedback
                    table_client.upsert_entity(feedback.to_table_entity())
                    feedback_count += 1

        except Exception as e:
            logger.warning(
                "pr_thread_fetch_failed",
                pr_id=pr_id,
                error=str(e)
            )

        return feedback_count

    async def _process_thread_feedback(
        self,
        thread: dict,
        pr_id: int,
        repository: str,
        project: str,
        review_id: str,
        issue_types: List[str]
    ) -> Optional[FeedbackEntity]:
        """
        Process a single PR thread for feedback signals.

        Args:
            thread: Thread data from Azure DevOps
            pr_id: Pull request ID
            repository: Repository name
            project: Project name
            review_id: Review ID
            issue_types: Issue types from original review

        Returns:
            FeedbackEntity if feedback found, None otherwise
        """
        thread_id = thread.get('id')
        status = thread.get('status', 'unknown').lower()

        # Check for resolved or won't fix status
        feedback_type = None
        is_positive = False

        if status == 'fixed' or status == 'closed':
            feedback_type = FeedbackType.THREAD_RESOLVED
            is_positive = True
        elif status == 'wontfix':
            feedback_type = FeedbackType.THREAD_WONT_FIX
            is_positive = False

        # Check for comment reactions (if available in thread properties)
        properties = thread.get('properties', {})

        # Azure DevOps may include reaction counts
        if 'thumbsUpCount' in properties and int(properties['thumbsUpCount']) > 0:
            feedback_type = FeedbackType.COMMENT_REACTION_UP
            is_positive = True
        elif 'thumbsDownCount' in properties and int(properties['thumbsDownCount']) > 0:
            feedback_type = FeedbackType.COMMENT_REACTION_DOWN
            is_positive = False

        if feedback_type is None:
            return None

        # Extract issue details from thread comments
        # The first comment usually contains our AI feedback
        comments = thread.get('comments', [])
        if not comments:
            return None

        first_comment = comments[0]
        comment_text = first_comment.get('content', '')

        # Try to extract issue type from comment
        # (Our comments should include this info)
        issue_type = "unknown"
        severity = "unknown"

        # Simple parsing - in production you'd have a more robust parser
        for itype in issue_types:
            if itype.lower() in comment_text.lower():
                issue_type = itype
                break

        # Extract file path from thread context
        thread_context = thread.get('threadContext', {})
        file_path = thread_context.get('filePath', 'unknown')

        # Get author
        author = first_comment.get('author', {}).get('displayName', 'unknown')

        # Parse published date safely
        published_date_str = first_comment.get('publishedDate')
        try:
            if published_date_str and isinstance(published_date_str, str):
                issue_created_at = datetime.fromisoformat(published_date_str.replace('Z', '+00:00'))
            else:
                issue_created_at = datetime.now(timezone.utc)
        except (ValueError, TypeError) as e:
            logger.warning(
                "invalid_published_date",
                published_date=published_date_str,
                error=str(e)
            )
            issue_created_at = datetime.now(timezone.utc)

        # Create feedback entity
        feedback = FeedbackEntity(
            PartitionKey=repository,
            RowKey=str(uuid.uuid4()),
            pr_id=pr_id,
            thread_id=thread_id,
            issue_type=issue_type,
            severity=severity,
            file_path=file_path,
            feedback_type=feedback_type,
            is_positive=is_positive,
            repository=repository,
            project=project,
            author=author,
            issue_created_at=issue_created_at,
            review_id=review_id
        )

        return feedback

    async def get_learning_context(self, repository: str) -> Dict:
        """
        Get learning context from past feedback for a repository.

        Analyzes historical feedback to determine:
        - High-value issue types (frequently accepted)
        - Low-value issue types (frequently rejected)
        - Team-specific patterns

        Args:
            repository: Repository name

        Returns:
            Dictionary with learning insights:
            {
                "high_value_issue_types": ["SecretExposed", "PublicEndpoint"],
                "low_value_issue_types": ["MinorStyle"],
                "positive_feedback_rate": 0.85,
                "total_feedback_count": 150,
                "issue_type_stats": {
                    "SecretExposed": {"positive": 45, "negative": 2},
                    ...
                }
            }
        """
        logger.info("learning_context_requested", repository=repository)

        ensure_table_exists('feedback')
        table_client = get_table_client('feedback')

        try:
            # Query all feedback for this repository
            safe_repository = sanitize_odata_value(repository)
            query_filter = f"PartitionKey eq '{safe_repository}'"

            # Use pagination to avoid loading all entities into memory
            feedback_entries = []
            for entry in query_entities_paginated(table_client, query_filter=query_filter, page_size=100):
                feedback_entries.append(entry)

            if not feedback_entries:
                logger.info("no_feedback_found", repository=repository)
                return {
                    "high_value_issue_types": [],
                    "low_value_issue_types": [],
                    "positive_feedback_rate": 0.0,
                    "total_feedback_count": 0,
                    "issue_type_stats": {}
                }

            # Analyze feedback by issue type
            issue_stats = defaultdict(lambda: {"positive": 0, "negative": 0})
            total_positive = 0
            total_negative = 0

            for entry in feedback_entries:
                issue_type = entry.get('issue_type', 'unknown')
                is_positive = entry.get('is_positive', False)

                if is_positive:
                    issue_stats[issue_type]["positive"] += 1
                    total_positive += 1
                else:
                    issue_stats[issue_type]["negative"] += 1
                    total_negative += 1

            # Calculate positive rate for each issue type
            issue_rates = {}
            for issue_type, stats in issue_stats.items():
                total = stats["positive"] + stats["negative"]
                if total > 0:
                    issue_rates[issue_type] = stats["positive"] / total

            # Identify high-value and low-value issue types
            # Require minimum samples to be statistically meaningful
            high_value = [
                itype for itype, rate in issue_rates.items()
                if rate > FEEDBACK_HIGH_VALUE_THRESHOLD and (issue_stats[itype]["positive"] + issue_stats[itype]["negative"]) >= FEEDBACK_MIN_SAMPLES
            ]

            low_value = [
                itype for itype, rate in issue_rates.items()
                if rate < FEEDBACK_LOW_VALUE_THRESHOLD and (issue_stats[itype]["positive"] + issue_stats[itype]["negative"]) >= FEEDBACK_MIN_SAMPLES
            ]

            total_feedback = total_positive + total_negative
            positive_rate = total_positive / total_feedback if total_feedback > 0 else 0.0

            context = {
                "high_value_issue_types": sorted(high_value),
                "low_value_issue_types": sorted(low_value),
                "positive_feedback_rate": round(positive_rate, 3),
                "total_feedback_count": total_feedback,
                "issue_type_stats": dict(issue_stats)
            }

            logger.info(
                "learning_context_generated",
                repository=repository,
                high_value_count=len(high_value),
                low_value_count=len(low_value),
                positive_rate=positive_rate
            )

            return context

        except Exception as e:
            logger.exception(
                "learning_context_error",
                repository=repository,
                error=str(e),
                error_type=type(e).__name__
            )
            # Return empty context on error
            return {
                "high_value_issue_types": [],
                "low_value_issue_types": [],
                "positive_feedback_rate": 0.0,
                "total_feedback_count": 0,
                "issue_type_stats": {},
                "error": str(e)
            }

    async def get_feedback_summary(self, days: int = PATTERN_ANALYSIS_DAYS) -> Dict:
        """
        Get summary of feedback across all repositories.

        Args:
            days: Number of days to include

        Returns:
            Summary statistics
        """
        ensure_table_exists('feedback')
        table_client = get_table_client('feedback')

        cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)

        try:
            # Query feedback from last N days
            query_filter = f"feedback_received_at ge datetime'{cutoff_time.isoformat()}'"

            # Use pagination to avoid loading all entities into memory
            feedback_entries = []
            for entry in query_entities_paginated(table_client, query_filter=query_filter, page_size=100):
                feedback_entries.append(entry)

            total_count = len(feedback_entries)
            positive_count = sum(1 for e in feedback_entries if e.get('is_positive'))
            negative_count = total_count - positive_count

            # Group by repository
            by_repository = Counter(e.get('repository') for e in feedback_entries)

            # Group by feedback type
            by_type = Counter(e.get('feedback_type') for e in feedback_entries)

            return {
                "days": days,
                "total_feedback": total_count,
                "positive_feedback": positive_count,
                "negative_feedback": negative_count,
                "positive_rate": positive_count / total_count if total_count > 0 else 0.0,
                "by_repository": dict(by_repository),
                "by_type": dict(by_type),
                "period_start": cutoff_time.isoformat(),
                "period_end": datetime.now(timezone.utc).isoformat()
            }

        except Exception as e:
            logger.exception("feedback_summary_error", error=str(e))
            return {"error": str(e)}
