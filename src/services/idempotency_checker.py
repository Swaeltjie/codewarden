# src/services/idempotency_checker.py
"""
Idempotency Checker

Prevents duplicate PR review processing when webhooks are retried.

Version: 2.5.11 - Centralized constants usage
"""
from typing import Optional, Dict
from datetime import datetime, timezone

from src.models.reliability import IdempotencyEntity
from src.utils.table_storage import (
    get_table_client,
    ensure_table_exists,
    query_entities_paginated
)
from src.utils.config import get_settings
from src.utils.constants import TABLE_STORAGE_BATCH_SIZE
from src.utils.logging import get_logger

logger = get_logger(__name__)


class IdempotencyChecker:
    """
    Manages request idempotency to prevent duplicate reviews.

    Features:
    - Checks if request already processed
    - Stores request metadata for deduplication
    - Automatic cleanup via Table Storage TTL (48 hours)
    - Handles webhook retries gracefully
    """

    def __init__(self):
        """Initialize idempotency checker."""
        self.settings = get_settings()
        self.table_name = 'idempotency'
        logger.info("idempotency_checker_initialized")

    async def is_duplicate_request(
        self,
        pr_id: int,
        repository: str,
        project: str,
        event_type: str,
        source_commit_id: Optional[str] = None
    ) -> tuple[bool, Optional[str]]:
        """
        Check if this request has already been processed.

        Args:
            pr_id: Pull request ID
            repository: Repository name
            project: Project name
            event_type: Event type (e.g., "pr.updated")
            source_commit_id: Latest commit ID (optional)

        Returns:
            Tuple of (is_duplicate, previous_result_summary)
            - is_duplicate: True if request already processed
            - previous_result_summary: Summary from previous processing (if duplicate)
        """
        try:
            ensure_table_exists(self.table_name)
            table_client = get_table_client(self.table_name)

            # Generate request ID
            request_id = IdempotencyEntity.create_request_id(
                pr_id=pr_id,
                repository=repository,
                event_type=event_type,
                source_commit_id=source_commit_id
            )

            # Check if entity exists
            partition_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")

            try:
                entity = table_client.get_entity(
                    partition_key=partition_key,
                    row_key=request_id
                )

                # Found existing request
                logger.info(
                    "duplicate_request_detected",
                    pr_id=pr_id,
                    repository=repository,
                    request_id=request_id,
                    first_processed_at=entity.get('first_processed_at'),
                    processing_count=entity.get('processing_count', 1)
                )

                # Update last seen time and increment count
                entity['last_seen_at'] = datetime.now(timezone.utc)
                entity['processing_count'] = entity.get('processing_count', 1) + 1
                table_client.update_entity(entity, mode='merge')

                return True, entity.get('result_summary', 'unknown')

            except (LookupError, KeyError) as e:
                # Entity not found - this is a new request
                logger.debug(
                    "new_request_detected",
                    pr_id=pr_id,
                    repository=repository,
                    request_id=request_id
                )
                return False, None
            except Exception as e:
                # Check for Azure-specific not found errors
                if "ResourceNotFound" in str(type(e).__name__) or "not found" in str(e).lower():
                    logger.debug(
                        "new_request_detected",
                        pr_id=pr_id,
                        repository=repository,
                        request_id=request_id
                    )
                    return False, None
                else:
                    # Unexpected error - log but don't block processing (fail open)
                    logger.warning(
                        "idempotency_check_failed",
                        pr_id=pr_id,
                        error=str(e),
                        error_type=type(e).__name__
                    )
                    return False, None

        except Exception as e:
            # Critical error in idempotency checking
            # Log but don't block processing (fail open)
            logger.exception(
                "idempotency_checker_error",
                pr_id=pr_id,
                repository=repository,
                error=str(e),
                error_type=type(e).__name__
            )
            return False, None

    async def record_request(
        self,
        pr_id: int,
        repository: str,
        project: str,
        event_type: str,
        source_commit_id: Optional[str] = None,
        result_summary: str = "processing"
    ) -> None:
        """
        Record that a request is being/has been processed.

        Args:
            pr_id: Pull request ID
            repository: Repository name
            project: Project name
            event_type: Event type
            source_commit_id: Latest commit ID (optional)
            result_summary: Brief summary of result
        """
        try:
            ensure_table_exists(self.table_name)
            table_client = get_table_client(self.table_name)

            # Create idempotency entity
            entity = IdempotencyEntity.from_pr_event(
                pr_id=pr_id,
                repository=repository,
                project=project,
                event_type=event_type,
                source_commit_id=source_commit_id,
                result_summary=result_summary
            )

            # Upsert entity
            table_client.upsert_entity(entity.to_table_entity())

            logger.info(
                "request_recorded",
                pr_id=pr_id,
                repository=repository,
                request_id=entity.RowKey,
                result_summary=result_summary
            )

        except Exception as e:
            # Don't fail the review if we can't record idempotency
            logger.warning(
                "idempotency_record_failed",
                pr_id=pr_id,
                repository=repository,
                error=str(e),
                error_type=type(e).__name__
            )

    async def update_result(
        self,
        pr_id: int,
        repository: str,
        event_type: str,
        source_commit_id: Optional[str],
        result_summary: str
    ) -> None:
        """
        Update the result summary for a processed request.

        Args:
            pr_id: Pull request ID
            repository: Repository name
            event_type: Event type
            source_commit_id: Latest commit ID (optional)
            result_summary: Summary of review result
        """
        try:
            ensure_table_exists(self.table_name)
            table_client = get_table_client(self.table_name)

            request_id = IdempotencyEntity.create_request_id(
                pr_id=pr_id,
                repository=repository,
                event_type=event_type,
                source_commit_id=source_commit_id
            )

            partition_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")

            # Get existing entity
            try:
                entity = table_client.get_entity(
                    partition_key=partition_key,
                    row_key=request_id
                )

                # Update result
                entity['result_summary'] = result_summary
                entity['last_seen_at'] = datetime.now(timezone.utc)

                table_client.update_entity(entity, mode='merge')

                logger.info(
                    "idempotency_result_updated",
                    pr_id=pr_id,
                    request_id=request_id,
                    result_summary=result_summary
                )

            except Exception as e:
                # Entity might not exist if record failed
                logger.debug(
                    "idempotency_update_skipped",
                    pr_id=pr_id,
                    reason=str(e)
                )

        except Exception as e:
            logger.warning(
                "idempotency_update_failed",
                pr_id=pr_id,
                error=str(e)
            )

    async def get_statistics(self, days: int = 7) -> Dict:
        """
        Get idempotency statistics.

        Args:
            days: Number of days to analyze

        Returns:
            Statistics dictionary
        """
        try:
            ensure_table_exists(self.table_name)
            table_client = get_table_client(self.table_name)

            # Query recent entries
            from datetime import timedelta
            start_date = datetime.now(timezone.utc) - timedelta(days=days)

            total_requests = 0
            duplicate_requests = 0

            # Use pagination to avoid loading all entities into memory
            for entity in query_entities_paginated(table_client, page_size=TABLE_STORAGE_BATCH_SIZE):
                total_requests += 1
                if entity.get('processing_count', 1) > 1:
                    duplicate_requests += 1

            duplicate_rate = (duplicate_requests / total_requests * 100.0) if total_requests > 0 else 0.0

            return {
                "total_requests": total_requests,
                "unique_requests": total_requests - duplicate_requests,
                "duplicate_requests": duplicate_requests,
                "duplicate_rate_percent": round(duplicate_rate, 2),
                "analysis_period_days": days
            }

        except Exception as e:
            logger.exception("idempotency_statistics_failed", error=str(e))
            return {
                "error": str(e),
                "total_requests": 0,
                "duplicate_requests": 0
            }
