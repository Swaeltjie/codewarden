# src/services/response_cache.py
"""
Response Cache

Caches AI review responses to reduce costs for identical diffs.

Version: 2.4.0 - Configurable TTL, storage rate limiting
"""
import structlog
import json
from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta

from src.models.reliability import CacheEntity
from src.models.review_result import ReviewResult
from src.utils.table_storage import (
    get_table_client,
    ensure_table_exists,
    sanitize_odata_value,
    query_entities_paginated
)
from src.utils.config import get_settings

logger = structlog.get_logger(__name__)


class ResponseCache:
    """
    Manages caching of AI review responses.

    Features:
    - Content-based hashing (same diff = cache hit)
    - 7-day TTL
    - Automatic cache invalidation
    - Cache hit tracking for analytics
    - Cost savings calculation
    - Storage rate limiting (v2.4.0)
    """

    # Default TTL reduced from 7 to 3 days to better align with feedback window
    DEFAULT_TTL_DAYS = 3

    # Storage rate limiting - max writes per minute
    MAX_WRITES_PER_MINUTE = 100
    _write_timestamps: list = []

    def __init__(self, ttl_days: int = None):
        """
        Initialize response cache.

        Args:
            ttl_days: Time-to-live in days (default: 3, configurable via CACHE_TTL_DAYS env var)
        """
        self.settings = get_settings()
        self.table_name = 'responsecache'

        # Use provided TTL, or check settings, or use default
        if ttl_days is not None:
            self.ttl_days = ttl_days
        else:
            self.ttl_days = getattr(self.settings, 'CACHE_TTL_DAYS', self.DEFAULT_TTL_DAYS)

        logger.info("response_cache_initialized", ttl_days=self.ttl_days)

    def _check_write_rate_limit(self) -> bool:
        """
        Check if write rate limit is exceeded.

        Returns:
            True if write is allowed, False if rate limited
        """
        now = datetime.now(timezone.utc).timestamp()
        window_start = now - 60  # 1 minute window

        # Clean old timestamps
        ResponseCache._write_timestamps = [
            ts for ts in ResponseCache._write_timestamps
            if ts > window_start
        ]

        # Check rate limit
        if len(ResponseCache._write_timestamps) >= self.MAX_WRITES_PER_MINUTE:
            logger.warning(
                "storage_write_rate_limited",
                writes_in_window=len(ResponseCache._write_timestamps),
                max_allowed=self.MAX_WRITES_PER_MINUTE
            )
            return False

        # Record this write
        ResponseCache._write_timestamps.append(now)
        return True

    def _is_safe_file_path(self, file_path: str) -> bool:
        """
        Validate that a file path is safe and doesn't contain malicious patterns.

        Args:
            file_path: Path to validate

        Returns:
            True if safe, False otherwise
        """
        import os
        from pathlib import Path

        # Check for null bytes
        if '\x00' in file_path:
            return False

        # Check for absolute paths (should be relative)
        if os.path.isabs(file_path):
            return False

        # Normalize the path and check for traversal
        try:
            normalized = os.path.normpath(file_path)

            # Check for path traversal patterns
            if '..' in Path(normalized).parts:
                return False

            # Check if normalized path starts with / or \ (absolute)
            if normalized.startswith(('/', '\\')):
                return False

        except (ValueError, OSError):
            return False

        # Check for suspicious patterns
        suspicious_patterns = [
            '../',
            '..\\',
            '/etc/',
            '/proc/',
            'c:\\',
            '\\windows\\',
        ]

        path_lower = file_path.lower()
        if any(pattern in path_lower for pattern in suspicious_patterns):
            return False

        return True

    async def get_cached_review(
        self,
        repository: str,
        diff_content: str,
        file_path: str
    ) -> Optional[ReviewResult]:
        """
        Get cached review result if available.

        Args:
            repository: Repository name
            diff_content: The diff content
            file_path: File path

        Returns:
            ReviewResult if cache hit, None if cache miss
        """
        try:
            # Validate file path for safety
            if not self._is_safe_file_path(file_path):
                logger.warning("unsafe_cache_file_path", file_path=file_path)
                return None

            ensure_table_exists(self.table_name)
            table_client = get_table_client(self.table_name)

            # Generate content hash
            content_hash = CacheEntity.create_content_hash(diff_content, file_path)

            # Try to fetch cached entity
            try:
                entity = table_client.get_entity(
                    partition_key=repository,
                    row_key=content_hash
                )

                # Check if cache entry is still valid
                expires_at = entity.get('expires_at')
                if isinstance(expires_at, str):
                    expires_at = datetime.fromisoformat(expires_at)

                now = datetime.now(timezone.utc)

                if expires_at and expires_at < now:
                    # Cache expired
                    logger.debug(
                        "cache_expired",
                        repository=repository,
                        file_path=file_path,
                        content_hash=content_hash,
                        expired_at=expires_at
                    )
                    # Delete expired entry
                    table_client.delete_entity(partition_key=repository, row_key=content_hash)
                    return None

                # Cache hit!
                logger.info(
                    "cache_hit",
                    repository=repository,
                    file_path=file_path,
                    content_hash=content_hash,
                    created_at=entity.get('created_at'),
                    hit_count=entity.get('hit_count', 1),
                    tokens_saved=entity.get('tokens_used', 0),
                    cost_saved=entity.get('estimated_cost', 0)
                )

                # Update hit count and last accessed time
                entity['hit_count'] = entity.get('hit_count', 1) + 1
                entity['last_accessed_at'] = now
                table_client.update_entity(entity, mode='merge')

                # Deserialize review result
                review_json = entity.get('review_result_json', '{}')
                review_data = json.loads(review_json)

                # Reconstruct ReviewResult
                review_result = ReviewResult(**review_data)

                return review_result

            except Exception as e:
                # Cache miss (entity not found)
                if "ResourceNotFound" in str(type(e).__name__) or "not found" in str(e).lower():
                    logger.debug(
                        "cache_miss",
                        repository=repository,
                        file_path=file_path,
                        content_hash=content_hash
                    )
                    return None
                else:
                    # Unexpected error
                    logger.warning(
                        "cache_retrieval_failed",
                        repository=repository,
                        file_path=file_path,
                        error=str(e),
                        error_type=type(e).__name__
                    )
                    return None

        except Exception as e:
            # Critical error - don't block review
            logger.exception(
                "cache_error",
                repository=repository,
                file_path=file_path,
                error=str(e)
            )
            return None

    async def cache_review(
        self,
        repository: str,
        diff_content: str,
        file_path: str,
        file_type: str,
        review_result: ReviewResult,
        tokens_used: int,
        estimated_cost: float,
        model_used: str
    ) -> None:
        """
        Cache a review result.

        Args:
            repository: Repository name
            diff_content: The diff content
            file_path: File path
            file_type: File type
            review_result: The review result to cache
            tokens_used: Tokens consumed
            estimated_cost: Cost in USD
            model_used: AI model identifier
        """
        try:
            # Validate file path for safety
            if not self._is_safe_file_path(file_path):
                logger.warning("unsafe_cache_file_path_store", file_path=file_path)
                return

            # Check storage rate limit
            if not self._check_write_rate_limit():
                logger.warning(
                    "cache_write_skipped_rate_limit",
                    repository=repository,
                    file_path=file_path
                )
                return

            ensure_table_exists(self.table_name)
            table_client = get_table_client(self.table_name)

            # Create cache entity
            cache_entity = CacheEntity.from_review_result(
                repository=repository,
                diff_content=diff_content,
                file_path=file_path,
                file_type=file_type,
                review_result=review_result,
                tokens_used=tokens_used,
                estimated_cost=estimated_cost,
                model_used=model_used,
                ttl_days=self.ttl_days
            )

            # Store in cache
            table_client.upsert_entity(cache_entity.to_table_entity())

            logger.info(
                "review_cached",
                repository=repository,
                file_path=file_path,
                content_hash=cache_entity.diff_hash,
                tokens=tokens_used,
                cost=estimated_cost,
                expires_at=cache_entity.expires_at
            )

        except Exception as e:
            # Don't fail the review if caching fails
            logger.warning(
                "cache_storage_failed",
                repository=repository,
                file_path=file_path,
                error=str(e),
                error_type=type(e).__name__
            )

    async def invalidate_cache(
        self,
        repository: str,
        file_path: Optional[str] = None
    ) -> int:
        """
        Invalidate cache entries.

        Args:
            repository: Repository name
            file_path: Optional specific file path to invalidate

        Returns:
            Number of entries invalidated
        """
        try:
            ensure_table_exists(self.table_name)
            table_client = get_table_client(self.table_name)

            count = 0

            if file_path:
                # Invalidate specific file
                # Need to query by file_path filter
                safe_repository = sanitize_odata_value(repository)
                safe_file_path = sanitize_odata_value(file_path)
                query_filter = f"PartitionKey eq '{safe_repository}' and file_path eq '{safe_file_path}'"

                # Use pagination to avoid loading all entities into memory
                for entity in query_entities_paginated(table_client, query_filter=query_filter, page_size=100):
                    table_client.delete_entity(
                        partition_key=repository,
                        row_key=entity['RowKey']
                    )
                    count += 1

                logger.info(
                    "cache_invalidated_file",
                    repository=repository,
                    file_path=file_path,
                    entries_deleted=count
                )
            else:
                # Invalidate entire repository
                safe_repository = sanitize_odata_value(repository)
                query_filter = f"PartitionKey eq '{safe_repository}'"

                # Use pagination to avoid loading all entities into memory
                for entity in query_entities_paginated(table_client, query_filter=query_filter, page_size=100):
                    table_client.delete_entity(
                        partition_key=repository,
                        row_key=entity['RowKey']
                    )
                    count += 1

                logger.info(
                    "cache_invalidated_repository",
                    repository=repository,
                    entries_deleted=count
                )

            return count

        except Exception as e:
            logger.exception(
                "cache_invalidation_failed",
                repository=repository,
                error=str(e)
            )
            return 0

    async def get_cache_statistics(self, repository: Optional[str] = None) -> Dict[str, Any]:
        """
        Get cache statistics.

        Args:
            repository: Optional repository to filter by

        Returns:
            Statistics dictionary
        """
        try:
            ensure_table_exists(self.table_name)
            table_client = get_table_client(self.table_name)

            # Query cache entries
            if repository:
                safe_repository = sanitize_odata_value(repository)
                query_filter = f"PartitionKey eq '{safe_repository}'"
            else:
                query_filter = None

            # Use pagination to process entries in batches (avoid OOM with large caches)
            total_entries = 0
            total_hits = 0
            total_tokens_saved = 0
            total_cost_saved = 0
            expired_count = 0
            reused_entries = 0
            now = datetime.now(timezone.utc)

            for entity in query_entities_paginated(table_client, query_filter=query_filter, page_size=100):
                total_entries += 1
                hit_count = entity.get('hit_count', 1)
                total_hits += hit_count

                # Calculate savings (exclude initial store)
                tokens = entity.get('tokens_used', 0)
                cost = entity.get('estimated_cost', 0)
                total_tokens_saved += tokens * (hit_count - 1)
                total_cost_saved += cost * (hit_count - 1)

                # Check if expired
                expires_at = entity.get('expires_at')
                if isinstance(expires_at, str):
                    expires_at = datetime.fromisoformat(expires_at)
                if expires_at and expires_at < now:
                    expired_count += 1

                # Check if reused
                if hit_count > 1:
                    reused_entries += 1

            # Cache reuse statistics
            # Note: hit_count starts at 1 for initial store, so actual cache hits = hit_count - 1
            # Prevent negative values from edge cases
            cache_hits = max(0, total_hits - total_entries)  # Subtract initial stores, ensure non-negative
            avg_reuse_per_entry = (cache_hits / total_entries) if total_entries > 0 else 0.0
            cache_efficiency_percent = (reused_entries / total_entries * 100.0) if total_entries > 0 else 0.0

            return {
                "repository": repository or "all",
                "total_cache_entries": total_entries,
                "expired_entries": expired_count,
                "active_entries": total_entries - expired_count,
                "total_cache_hits": cache_hits,
                "reused_entries": reused_entries,
                "cache_efficiency_percent": round(cache_efficiency_percent, 2),
                "avg_reuse_per_entry": round(avg_reuse_per_entry, 2),
                "tokens_saved": total_tokens_saved,
                "cost_saved_usd": round(total_cost_saved, 4),
                "analyzed_at": datetime.now(timezone.utc).isoformat()
            }

        except Exception as e:
            logger.exception("cache_statistics_failed", error=str(e))
            return {
                "error": str(e),
                "total_cache_entries": 0,
                "tokens_saved": 0,
                "cost_saved_usd": 0.0
            }

    async def cleanup_expired_entries(self) -> int:
        """
        Clean up expired cache entries.

        Uses pagination to avoid loading all entries into memory at once.

        Returns:
            Number of entries deleted
        """
        try:
            ensure_table_exists(self.table_name)
            table_client = get_table_client(self.table_name)

            now = datetime.now(timezone.utc)
            deleted_count = 0

            # Process entries in paginated batches
            for entity in query_entities_paginated(table_client, page_size=100):
                expires_at = entity.get('expires_at')
                if isinstance(expires_at, str):
                    expires_at = datetime.fromisoformat(expires_at)

                if expires_at and expires_at < now:
                    # Delete expired entry
                    table_client.delete_entity(
                        partition_key=entity['PartitionKey'],
                        row_key=entity['RowKey']
                    )
                    deleted_count += 1

            logger.info(
                "cache_cleanup_completed",
                deleted_count=deleted_count
            )

            return deleted_count

        except Exception as e:
            logger.exception("cache_cleanup_failed", error=str(e))
            return 0
