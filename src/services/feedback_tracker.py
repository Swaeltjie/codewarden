# src/services/feedback_tracker.py
"""
Feedback Tracker

Tracks developer feedback on AI suggestions to improve over time.
Supports few-shot learning with accepted examples and rejection patterns.

Version: 2.7.0 - Added few-shot learning with examples and rejection patterns
"""
import asyncio
import uuid
import json
import re
from typing import Dict, List, Optional, Union
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict

from src.utils.table_storage import (
    get_table_client,
    ensure_table_exists,
    sanitize_odata_value,
    query_entities_paginated,
)
from src.models.feedback import (
    FeedbackEntity,
    FeedbackType,
    FeedbackExample,
    RejectionPattern,
    LearningContext,
)
from src.services.azure_devops import AzureDevOpsClient
from src.utils.config import get_settings
from src.utils.constants import (
    FEEDBACK_TABLE_NAME,
    FEEDBACK_MIN_SAMPLES,
    FEEDBACK_HIGH_VALUE_THRESHOLD,
    FEEDBACK_LOW_VALUE_THRESHOLD,
    PATTERN_ANALYSIS_DAYS,
    TABLE_STORAGE_BATCH_SIZE,
    MAX_EXAMPLES_PER_ISSUE_TYPE,
    MAX_EXAMPLE_CODE_SNIPPET_LENGTH,
    MAX_EXAMPLE_SUGGESTION_LENGTH,
    LEARNING_CONTEXT_DAYS,
    MIN_REJECTIONS_FOR_PATTERN,
    MAX_REJECTION_PATTERNS,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


class FeedbackTracker:
    """
    Tracks and analyzes developer feedback on AI suggestions.

    Features:
    - Monitors PR thread reactions (thumbs up/down)
    - Tracks resolved vs won't fix status
    - Learns which issue types are valuable
    - Adjusts review focus based on team preferences
    """

    def __init__(self) -> None:
        """Initialize feedback tracker."""
        self.settings = get_settings()
        self.devops_client: Optional[AzureDevOpsClient] = None
        logger.info("feedback_tracker_initialized")

    async def _get_devops_client(self) -> AzureDevOpsClient:
        """Get or create Azure DevOps client."""
        if self.devops_client is None:
            self.devops_client = AzureDevOpsClient()
        return self.devops_client

    async def close(self) -> None:
        """Close resources."""
        if self.devops_client:
            await self.devops_client.close()
            self.devops_client = None
        logger.debug("feedback_tracker_closed")

    async def __aenter__(self) -> "FeedbackTracker":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
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

        # v2.6.3: Run blocking table operations in thread pool
        await asyncio.to_thread(ensure_table_exists, "feedback")
        table_client = get_table_client("feedback")

        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        feedback_collected = 0

        try:
            # Get recent reviews from history to find relevant PRs
            # v2.6.3: Ensure reviewhistory table exists
            await asyncio.to_thread(ensure_table_exists, "reviewhistory")
            history_table = get_table_client("reviewhistory")

            # Query reviews from the last N hours
            # Note: reviewed_at is stored as ISO string
            # Use OData datetime format for consistency with pattern_detector.py
            query_filter = f"reviewed_at ge datetime'{cutoff_time.isoformat()}'"

            # v2.6.3: Use pagination with non-blocking thread pool
            recent_reviews = await asyncio.to_thread(
                lambda: list(
                    query_entities_paginated(
                        history_table,
                        query_filter=query_filter,
                        page_size=TABLE_STORAGE_BATCH_SIZE,
                    )
                )
            )

            logger.info("recent_reviews_found", count=len(recent_reviews), hours=hours)

            # For each recent review, check for feedback
            for review in recent_reviews:
                try:
                    feedback_count = await self._collect_pr_feedback(
                        review, table_client
                    )
                    feedback_collected += feedback_count

                except Exception as e:
                    logger.warning(
                        "pr_feedback_collection_failed",
                        pr_id=review.get("pr_id"),
                        repository=review.get("repository"),
                        error=str(e),
                    )
                    continue

            logger.info(
                "feedback_collection_completed",
                feedback_entries=feedback_collected,
                reviews_checked=len(recent_reviews),
            )

            return feedback_collected

        except Exception as e:
            logger.exception(
                "feedback_collection_error",
                hours=hours,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    async def _collect_pr_feedback(self, review: dict, table_client) -> int:
        """
        Collect feedback for a specific PR review.

        Args:
            review: Review history entity
            table_client: Table client for storing feedback

        Returns:
            Number of feedback items collected for this PR
        """
        devops = await self._get_devops_client()

        pr_id = review.get("pr_id")
        repository = review.get("repository")
        project = review.get("project")

        if not all([pr_id, repository, project]):
            logger.warning("missing_pr_metadata", review_id=review.get("RowKey"))
            return 0

        feedback_count = 0

        try:
            # Get PR threads/comments
            # Get repository_id from review data - prefer explicit field over PartitionKey
            repository_id = review.get("repository_id") or review.get("PartitionKey")

            # Validate repository_id format (Azure DevOps uses UUID format)
            if not repository_id:
                logger.warning(
                    "missing_repository_id", review_id=review.get("RowKey"), pr_id=pr_id
                )
                return 0

            # Validate UUID format for repository_id
            uuid_pattern = (
                r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
            )
            if not re.match(uuid_pattern, repository_id, re.IGNORECASE):
                logger.warning(
                    "invalid_repository_id_format",
                    repository_id=repository_id[:50] if repository_id else None,
                    review_id=review.get("RowKey"),
                )
                return 0

            threads = await devops._get_pr_threads(project, repository_id, pr_id)

            # Parse issue types from review
            issue_types = json.loads(review.get("issue_types", "[]"))

            # Process each thread for feedback (with per-thread error handling)
            for thread in threads:
                try:
                    feedback = await self._process_thread_feedback(
                        thread=thread,
                        pr_id=pr_id,
                        repository=repository,
                        project=project,
                        review_id=review.get("RowKey"),
                        issue_types=issue_types,
                    )

                    if feedback:
                        # v2.6.3: Non-blocking upsert
                        await asyncio.to_thread(
                            table_client.upsert_entity, feedback.to_table_entity()
                        )
                        feedback_count += 1
                except Exception as e:
                    # Log and continue processing remaining threads
                    logger.warning(
                        "thread_feedback_processing_failed",
                        thread_id=thread.get("id"),
                        pr_id=pr_id,
                        error=str(e),
                        error_type=type(e).__name__,
                    )
                    continue

        except Exception as e:
            logger.warning("pr_thread_fetch_failed", pr_id=pr_id, error=str(e))

        return feedback_count

    async def _process_thread_feedback(
        self,
        thread: dict,
        pr_id: int,
        repository: str,
        project: str,
        review_id: str,
        issue_types: List[str],
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
        thread_id = thread.get("id")
        status = thread.get("status", "unknown").lower()

        # Check for resolved or won't fix status
        feedback_type = None
        is_positive = False

        if status == "fixed" or status == "closed":
            feedback_type = FeedbackType.THREAD_RESOLVED
            is_positive = True
        elif status == "wontfix":
            feedback_type = FeedbackType.THREAD_WONT_FIX
            is_positive = False

        # Check for comment reactions (if available in thread properties)
        properties = thread.get("properties", {})

        # Validate properties is a dict (malformed API response protection)
        if not isinstance(properties, dict):
            logger.warning("invalid_properties_structure", thread_id=thread.get("id"))
            properties = {}

        # Azure DevOps may include reaction counts
        try:
            if "thumbsUpCount" in properties and int(properties["thumbsUpCount"]) > 0:
                feedback_type = FeedbackType.COMMENT_REACTION_UP
                is_positive = True
            elif (
                "thumbsDownCount" in properties
                and int(properties["thumbsDownCount"]) > 0
            ):
                feedback_type = FeedbackType.COMMENT_REACTION_DOWN
                is_positive = False
        except (ValueError, TypeError) as e:
            logger.warning(
                "invalid_reaction_count", thread_id=thread.get("id"), error=str(e)
            )

        if feedback_type is None:
            return None

        # Extract issue details from thread comments
        # The first comment usually contains our AI feedback
        comments = thread.get("comments", [])
        if not comments:
            return None

        first_comment = comments[0]
        comment_text = first_comment.get("content", "")

        # Try to extract issue type from comment
        # (Our comments should include this info)
        issue_type = "unknown"
        severity = "medium"  # Default to valid severity value

        # Simple parsing - in production you'd have a more robust parser
        for itype in issue_types:
            if itype.lower() in comment_text.lower():
                issue_type = itype
                break

        # Extract severity from comment text
        comment_lower = comment_text.lower()
        for sev in ["critical", "high", "medium", "low", "info"]:
            if sev in comment_lower:
                severity = sev
                break

        # Extract file path from thread context
        thread_context = thread.get("threadContext", {})
        file_path = thread_context.get("filePath", "unknown")

        # Get author
        author = first_comment.get("author", {}).get("displayName", "unknown")

        # Parse published date safely
        published_date_str = first_comment.get("publishedDate")
        try:
            if published_date_str and isinstance(published_date_str, str):
                issue_created_at = datetime.fromisoformat(
                    published_date_str.replace("Z", "+00:00")
                )
            else:
                issue_created_at = datetime.now(timezone.utc)
        except (ValueError, TypeError) as e:
            logger.warning(
                "invalid_published_date",
                published_date=published_date_str,
                error=str(e),
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
            review_id=review_id,
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

        # v2.6.3: Run blocking table operations in thread pool
        await asyncio.to_thread(ensure_table_exists, "feedback")
        table_client = get_table_client("feedback")

        try:
            # Query all feedback for this repository
            safe_repository = sanitize_odata_value(repository)
            query_filter = f"PartitionKey eq '{safe_repository}'"

            # v2.6.3: Use pagination with non-blocking thread pool
            feedback_entries = await asyncio.to_thread(
                lambda: list(
                    query_entities_paginated(
                        table_client,
                        query_filter=query_filter,
                        page_size=TABLE_STORAGE_BATCH_SIZE,
                    )
                )
            )

            if not feedback_entries:
                logger.info("no_feedback_found", repository=repository)
                return {
                    "high_value_issue_types": [],
                    "low_value_issue_types": [],
                    "positive_feedback_rate": 0.0,
                    "total_feedback_count": 0,
                    "issue_type_stats": {},
                }

            # Analyze feedback by issue type
            issue_stats = defaultdict(lambda: {"positive": 0, "negative": 0})
            total_positive = 0
            total_negative = 0

            for entry in feedback_entries:
                issue_type = entry.get("issue_type", "unknown")
                is_positive = entry.get("is_positive", False)

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
                itype
                for itype, rate in issue_rates.items()
                if rate > FEEDBACK_HIGH_VALUE_THRESHOLD
                and (issue_stats[itype]["positive"] + issue_stats[itype]["negative"])
                >= FEEDBACK_MIN_SAMPLES
            ]

            low_value = [
                itype
                for itype, rate in issue_rates.items()
                if rate < FEEDBACK_LOW_VALUE_THRESHOLD
                and (issue_stats[itype]["positive"] + issue_stats[itype]["negative"])
                >= FEEDBACK_MIN_SAMPLES
            ]

            total_feedback = total_positive + total_negative
            positive_rate = (
                total_positive / total_feedback if total_feedback > 0 else 0.0
            )

            context = {
                "high_value_issue_types": sorted(high_value),
                "low_value_issue_types": sorted(low_value),
                "positive_feedback_rate": round(positive_rate, 3),
                "total_feedback_count": total_feedback,
                "issue_type_stats": dict(issue_stats),
            }

            logger.info(
                "learning_context_generated",
                repository=repository,
                high_value_count=len(high_value),
                low_value_count=len(low_value),
                positive_rate=positive_rate,
            )

            return context

        except Exception as e:
            logger.exception(
                "learning_context_error",
                repository=repository,
                error=str(e),
                error_type=type(e).__name__,
            )
            # Return empty context on error
            return {
                "high_value_issue_types": [],
                "low_value_issue_types": [],
                "positive_feedback_rate": 0.0,
                "total_feedback_count": 0,
                "issue_type_stats": {},
                "error": str(e),
            }

    async def get_feedback_summary(self, days: int = PATTERN_ANALYSIS_DAYS) -> Dict:
        """
        Get summary of feedback across all repositories.

        Args:
            days: Number of days to include (1-365)

        Returns:
            Summary statistics
        """
        # Validate days parameter (prevents DoS via excessive date range queries)
        if not isinstance(days, int) or days < 1 or days > 365:
            logger.warning("invalid_days_parameter", days=days)
            return {
                "error": "days must be an integer between 1 and 365",
                "total_feedback": 0,
                "positive_feedback": 0,
                "negative_feedback": 0,
            }

        # v2.6.3: Run blocking table operations in thread pool
        await asyncio.to_thread(ensure_table_exists, "feedback")
        table_client = get_table_client("feedback")

        cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)

        try:
            # Query feedback from last N days
            # Use OData datetime format for consistency across codebase
            query_filter = (
                f"feedback_received_at ge datetime'{cutoff_time.isoformat()}'"
            )

            # v2.6.3: Use pagination with non-blocking thread pool
            feedback_entries = await asyncio.to_thread(
                lambda: list(
                    query_entities_paginated(
                        table_client,
                        query_filter=query_filter,
                        page_size=TABLE_STORAGE_BATCH_SIZE,
                    )
                )
            )

            total_count = len(feedback_entries)
            positive_count = sum(1 for e in feedback_entries if e.get("is_positive"))
            negative_count = total_count - positive_count

            # Group by repository
            by_repository = Counter(e.get("repository") for e in feedback_entries)

            # Group by feedback type
            by_type = Counter(e.get("feedback_type") for e in feedback_entries)

            return {
                "days": days,
                "total_feedback": total_count,
                "positive_feedback": positive_count,
                "negative_feedback": negative_count,
                "positive_rate": (
                    positive_count / total_count if total_count > 0 else 0.0
                ),
                "by_repository": dict(by_repository),
                "by_type": dict(by_type),
                "period_start": cutoff_time.isoformat(),
                "period_end": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.exception("feedback_summary_error", error=str(e))
            return {"error": str(e)}

    async def _extract_accepted_examples(
        self,
        feedback_entries: List[dict],
        repository: str,
    ) -> Dict[str, List[FeedbackExample]]:
        """
        Extract few-shot examples from accepted suggestions.

        Identifies suggestions that were marked as resolved/accepted and
        extracts them as examples for prompt injection.

        Args:
            feedback_entries: List of feedback entity dicts from table storage
            repository: Repository name for logging

        Returns:
            Dictionary mapping issue_type to list of FeedbackExample objects
        """
        examples: Dict[str, List[FeedbackExample]] = defaultdict(list)

        # Filter to positive feedback only (with type validation)
        positive_entries = [
            e
            for e in feedback_entries
            if isinstance(e, dict) and e.get("is_positive") is True
        ]

        if not positive_entries:
            logger.debug("no_positive_feedback", repository=repository)
            return dict(examples)

        # Group by issue type and extract best examples
        by_issue_type: Dict[str, List[dict]] = defaultdict(list)
        for entry in positive_entries:
            issue_type = entry.get("issue_type", "unknown")
            if issue_type and issue_type != "unknown":
                by_issue_type[issue_type].append(entry)

        # Helper to safely parse datetime for sorting
        def get_feedback_datetime(entry: dict) -> datetime:
            dt_str = entry.get("feedback_received_at", "")
            if not dt_str:
                return datetime.min.replace(tzinfo=timezone.utc)
            try:
                dt = datetime.fromisoformat(str(dt_str).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except (ValueError, TypeError):
                return datetime.min.replace(tzinfo=timezone.utc)

        # For each issue type, create FeedbackExample objects
        for issue_type, entries in by_issue_type.items():
            # Sort by recency (most recent first) using proper datetime comparison
            sorted_entries = sorted(
                entries,
                key=get_feedback_datetime,
                reverse=True,
            )

            # Take up to MAX_EXAMPLES_PER_ISSUE_TYPE
            for entry in sorted_entries[:MAX_EXAMPLES_PER_ISSUE_TYPE]:
                try:
                    # Extract code snippet from file_path context
                    # In real implementation, we'd fetch from cache or PR data
                    file_path = entry.get("file_path", "unknown")

                    # Create example with truncated content
                    example = FeedbackExample(
                        issue_type=issue_type,
                        code_snippet=f"[Code from {file_path}]"[
                            :MAX_EXAMPLE_CODE_SNIPPET_LENGTH
                        ],
                        suggestion=f"Issue flagged and accepted by team"[
                            :MAX_EXAMPLE_SUGGESTION_LENGTH
                        ],
                        file_path=file_path[:500],
                        severity=entry.get("severity", "medium"),
                        acceptance_count=1,
                    )
                    examples[issue_type].append(example)

                except Exception as e:
                    logger.warning(
                        "example_extraction_failed",
                        issue_type=issue_type,
                        error=str(e),
                    )
                    continue

        logger.info(
            "examples_extracted",
            repository=repository,
            issue_types=len(examples),
            total_examples=sum(len(v) for v in examples.values()),
        )

        return dict(examples)

    async def _analyze_rejection_patterns(
        self,
        feedback_entries: List[dict],
        repository: str,
    ) -> List[RejectionPattern]:
        """
        Analyze patterns in rejected suggestions.

        Identifies issue types that are consistently rejected by the team
        to help reduce false positives in future reviews.

        Args:
            feedback_entries: List of feedback entity dicts from table storage
            repository: Repository name for logging

        Returns:
            List of RejectionPattern objects
        """
        patterns: List[RejectionPattern] = []

        # Filter to negative feedback only (explicit False check)
        negative_entries = [
            e
            for e in feedback_entries
            if isinstance(e, dict) and e.get("is_positive") is False
        ]

        if not negative_entries:
            logger.debug("no_negative_feedback", repository=repository)
            return patterns

        # Count rejections by issue type
        rejection_counts: Counter = Counter()
        sample_contexts: Dict[str, str] = {}

        for entry in negative_entries:
            issue_type = entry.get("issue_type", "unknown")
            if issue_type and issue_type != "unknown":
                rejection_counts[issue_type] += 1
                # Keep first file_path as sample context
                if issue_type not in sample_contexts:
                    sample_contexts[issue_type] = entry.get("file_path", "")[:200]

        # Create patterns for issue types with significant rejections
        for issue_type, count in rejection_counts.most_common(MAX_REJECTION_PATTERNS):
            if count >= MIN_REJECTIONS_FOR_PATTERN:
                pattern = RejectionPattern(
                    issue_type=issue_type,
                    reason=f"Rejected {count} times by the team",
                    rejection_count=count,
                    sample_context=sample_contexts.get(issue_type),
                )
                patterns.append(pattern)

        logger.info(
            "rejection_patterns_analyzed",
            repository=repository,
            patterns_found=len(patterns),
            total_rejections=len(negative_entries),
        )

        return patterns

    async def get_enhanced_learning_context(
        self,
        repository: str,
        days: int = LEARNING_CONTEXT_DAYS,
    ) -> LearningContext:
        """
        Get enhanced learning context with few-shot examples and rejection patterns.

        Builds on the basic learning context to include:
        - Few-shot examples from accepted suggestions
        - Rejection patterns to avoid
        - Full LearningContext model

        Args:
            repository: Repository name
            days: Number of days of feedback to analyze (1-365)

        Returns:
            LearningContext object with examples and patterns
        """
        logger.info(
            "enhanced_learning_context_requested",
            repository=repository,
            days=days,
        )

        # Validate days parameter
        days = max(1, min(365, days))

        # Ensure table exists
        await asyncio.to_thread(ensure_table_exists, "feedback")
        table_client = get_table_client("feedback")

        cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)

        try:
            # Query feedback for this repository within time window
            safe_repository = sanitize_odata_value(repository)
            query_filter = (
                f"PartitionKey eq '{safe_repository}' and "
                f"feedback_received_at ge datetime'{cutoff_time.isoformat()}'"
            )

            feedback_entries = await asyncio.to_thread(
                lambda: list(
                    query_entities_paginated(
                        table_client,
                        query_filter=query_filter,
                        page_size=TABLE_STORAGE_BATCH_SIZE,
                    )
                )
            )

            # Calculate basic statistics
            issue_stats: Dict[str, Dict[str, int]] = defaultdict(
                lambda: {"positive": 0, "negative": 0}
            )
            total_positive = 0
            total_negative = 0

            for entry in feedback_entries:
                try:
                    # Validate entry is a dictionary
                    if not isinstance(entry, dict):
                        logger.warning(
                            "invalid_feedback_entry_type",
                            entry_type=type(entry).__name__,
                        )
                        continue

                    issue_type = entry.get("issue_type", "unknown")
                    is_positive = entry.get("is_positive", False)

                    if is_positive:
                        issue_stats[issue_type]["positive"] += 1
                        total_positive += 1
                    else:
                        issue_stats[issue_type]["negative"] += 1
                        total_negative += 1
                except Exception as e:
                    # Log and continue - one bad entry shouldn't fail entire context
                    logger.warning(
                        "feedback_entry_processing_failed",
                        error=str(e),
                        error_type=type(e).__name__,
                    )
                    continue

            # Calculate rates and categorize issue types
            high_value: List[str] = []
            low_value: List[str] = []

            for issue_type, stats in issue_stats.items():
                total = stats["positive"] + stats["negative"]
                if total >= FEEDBACK_MIN_SAMPLES:
                    rate = stats["positive"] / total
                    if rate >= FEEDBACK_HIGH_VALUE_THRESHOLD:
                        high_value.append(issue_type)
                    elif rate <= FEEDBACK_LOW_VALUE_THRESHOLD:
                        low_value.append(issue_type)

            total_feedback = total_positive + total_negative
            positive_rate = (
                total_positive / total_feedback if total_feedback > 0 else 0.0
            )

            # Extract few-shot examples
            examples = await self._extract_accepted_examples(
                feedback_entries, repository
            )

            # Analyze rejection patterns
            rejection_patterns = await self._analyze_rejection_patterns(
                feedback_entries, repository
            )

            # Build LearningContext
            context = LearningContext(
                repository=repository,
                high_value_issue_types=sorted(high_value),
                low_value_issue_types=sorted(low_value),
                positive_feedback_rate=round(positive_rate, 3),
                total_feedback_count=total_feedback,
                issue_type_stats=dict(issue_stats),
                examples=examples,
                rejection_patterns=rejection_patterns,
                days_analyzed=days,
            )

            logger.info(
                "enhanced_learning_context_generated",
                repository=repository,
                high_value_count=len(high_value),
                low_value_count=len(low_value),
                examples_count=sum(len(v) for v in examples.values()),
                patterns_count=len(rejection_patterns),
                positive_rate=positive_rate,
            )

            return context

        except Exception as e:
            logger.exception(
                "enhanced_learning_context_error",
                repository=repository,
                error=str(e),
                error_type=type(e).__name__,
            )
            # Return empty context on error
            return LearningContext(
                repository=repository,
                days_analyzed=days,
            )
