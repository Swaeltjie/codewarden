# src/models/reliability.py
"""
Reliability Models

Data models for idempotency tracking and response caching.

Version: 2.3.0
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
import hashlib
import json


class IdempotencyEntity(BaseModel):
    """
    Tracks processed requests to prevent duplicate processing.

    Storage Strategy:
    - PartitionKey: Date (YYYY-MM-DD) for efficient querying and auto-cleanup
    - RowKey: Request ID (PR ID + event type hash)
    - TTL: 48 hours via Table Storage lifecycle policy
    """
    PartitionKey: str  # Date: YYYY-MM-DD
    RowKey: str  # Request ID
    pr_id: int
    repository: str
    project: str
    event_type: str  # "pr.created", "pr.updated", etc.
    first_processed_at: datetime
    last_seen_at: datetime
    processing_count: int = 1
    result_summary: str  # Brief summary of review result

    @classmethod
    def create_request_id(
        cls,
        pr_id: int,
        repository: str,
        event_type: str,
        source_commit_id: Optional[str] = None
    ) -> str:
        """
        Generate deterministic request ID.

        Args:
            pr_id: Pull request ID
            repository: Repository name
            event_type: Webhook event type
            source_commit_id: Latest commit ID (optional, makes ID more specific)

        Returns:
            Unique request ID string
        """
        # Create stable hash of request parameters
        parts = [
            str(pr_id),
            repository,
            event_type
        ]
        if source_commit_id:
            parts.append(source_commit_id)

        content = "|".join(parts)
        request_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

        return f"pr{pr_id}_{request_hash}"

    @classmethod
    def from_pr_event(
        cls,
        pr_id: int,
        repository: str,
        project: str,
        event_type: str,
        source_commit_id: Optional[str] = None,
        result_summary: str = "pending"
    ) -> "IdempotencyEntity":
        """Create IdempotencyEntity from PR event data."""
        now = datetime.now(timezone.utc)
        request_id = cls.create_request_id(pr_id, repository, event_type, source_commit_id)

        return cls(
            PartitionKey=now.strftime("%Y-%m-%d"),
            RowKey=request_id,
            pr_id=pr_id,
            repository=repository,
            project=project,
            event_type=event_type,
            first_processed_at=now,
            last_seen_at=now,
            processing_count=1,
            result_summary=result_summary
        )

    def to_table_entity(self) -> Dict[str, Any]:
        """Convert to Azure Table Storage entity."""
        return {
            "PartitionKey": self.PartitionKey,
            "RowKey": self.RowKey,
            "pr_id": self.pr_id,
            "repository": self.repository,
            "project": self.project,
            "event_type": self.event_type,
            "first_processed_at": self.first_processed_at,
            "last_seen_at": self.last_seen_at,
            "processing_count": self.processing_count,
            "result_summary": self.result_summary
        }


class CacheEntity(BaseModel):
    """
    Caches AI review responses to reduce costs for identical diffs.

    Storage Strategy:
    - PartitionKey: Repository name (for efficient cleanup)
    - RowKey: Content hash (SHA256 of diff content)
    - TTL: 7 days
    """
    PartitionKey: str  # Repository name
    RowKey: str  # Content hash (SHA256)
    diff_hash: str
    file_path: str
    file_type: str
    review_result_json: str  # Serialized ReviewResult
    tokens_used: int
    estimated_cost: float
    model_used: str
    created_at: datetime
    last_accessed_at: datetime
    hit_count: int = 1
    expires_at: datetime  # 7 days from creation

    @classmethod
    def create_content_hash(cls, diff_content: str, file_path: str) -> str:
        """
        Generate deterministic content hash for caching.

        Args:
            diff_content: The actual diff content
            file_path: File path (adds specificity)

        Returns:
            SHA256 hash string
        """
        # Normalize diff content (remove timestamps, whitespace variations)
        normalized = diff_content.strip()
        content = f"{file_path}:{normalized}"

        return hashlib.sha256(content.encode()).hexdigest()

    @classmethod
    def from_review_result(
        cls,
        repository: str,
        diff_content: str,
        file_path: str,
        file_type: str,
        review_result: Any,  # ReviewResult object
        tokens_used: int,
        estimated_cost: float,
        model_used: str,
        ttl_days: int = 7
    ) -> "CacheEntity":
        """Create CacheEntity from review result."""
        now = datetime.now(timezone.utc)
        content_hash = cls.create_content_hash(diff_content, file_path)

        # Serialize review result
        review_json = review_result.model_dump_json() if hasattr(review_result, 'model_dump_json') else json.dumps(review_result)

        return cls(
            PartitionKey=repository,
            RowKey=content_hash,
            diff_hash=content_hash,
            file_path=file_path,
            file_type=file_type,
            review_result_json=review_json,
            tokens_used=tokens_used,
            estimated_cost=estimated_cost,
            model_used=model_used,
            created_at=now,
            last_accessed_at=now,
            hit_count=1,
            expires_at=now + timedelta(days=ttl_days)
        )

    def to_table_entity(self) -> Dict[str, Any]:
        """Convert to Azure Table Storage entity."""
        return {
            "PartitionKey": self.PartitionKey,
            "RowKey": self.RowKey,
            "diff_hash": self.diff_hash,
            "file_path": self.file_path,
            "file_type": self.file_type,
            "review_result_json": self.review_result_json,
            "tokens_used": self.tokens_used,
            "estimated_cost": self.estimated_cost,
            "model_used": self.model_used,
            "created_at": self.created_at,
            "last_accessed_at": self.last_accessed_at,
            "hit_count": self.hit_count,
            "expires_at": self.expires_at
        }


class CircuitBreakerState(BaseModel):
    """
    Tracks circuit breaker state for external service.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Too many failures, requests fail fast
    - HALF_OPEN: Testing if service recovered
    """
    service_name: str
    state: str  # "CLOSED", "OPEN", "HALF_OPEN"
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[datetime] = None
    last_state_change: datetime
    next_retry_time: Optional[datetime] = None

    def record_success(self, success_threshold: int = 2) -> None:
        """
        Record successful request.

        Args:
            success_threshold: Number of successes needed to close from HALF_OPEN
        """
        self.success_count += 1
        self.failure_count = 0

        if self.state == "HALF_OPEN":
            # In HALF_OPEN state, require success_threshold successes to close
            if self.success_count >= success_threshold:
                self.state = "CLOSED"
                self.last_state_change = datetime.now(timezone.utc)
                self.success_count = 0  # Reset counter
        elif self.state != "CLOSED":
            # For any other state, transition to CLOSED immediately
            self.state = "CLOSED"
            self.last_state_change = datetime.now(timezone.utc)

    def record_failure(self, failure_threshold: int = 5, timeout_seconds: int = 60) -> None:
        """Record failed request and potentially open circuit."""
        now = datetime.now(timezone.utc)
        self.failure_count += 1
        self.last_failure_time = now

        if self.failure_count >= failure_threshold and self.state == "CLOSED":
            # Open the circuit
            self.state = "OPEN"
            self.last_state_change = now
            self.next_retry_time = now + timedelta(seconds=timeout_seconds)

    def should_allow_request(self) -> bool:
        """
        Check if request should be allowed through.

        IMPORTANT: This method does NOT modify state. State transitions
        happen under lock protection in CircuitBreaker.call().

        Returns:
            True if request should be allowed, False otherwise
        """
        now = datetime.now(timezone.utc)

        if self.state == "CLOSED":
            return True

        if self.state == "OPEN":
            # Check if cooldown period has passed (but don't transition yet)
            if self.next_retry_time and now >= self.next_retry_time:
                return True  # Will transition to HALF_OPEN in call() under lock
            return False

        if self.state == "HALF_OPEN":
            # Allow request to test recovery
            return True

        return False
