# src/models/reliability.py
"""
Reliability Models

Data models for idempotency tracking and response caching.

Version: 2.7.2 - Fixed HALF_OPEN failure handling to properly reopen circuit
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator
import hashlib
import json

from src.utils.constants import (
    DEFAULT_CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    DEFAULT_CIRCUIT_BREAKER_TIMEOUT_SECONDS,
)


class IdempotencyEntity(BaseModel):
    """
    Tracks processed requests to prevent duplicate processing.

    Storage Strategy:
    - PartitionKey: Date (YYYY-MM-DD) for efficient querying and auto-cleanup
    - RowKey: Request ID (PR ID + event type hash)
    - TTL: 48 hours via Table Storage lifecycle policy
    """

    PartitionKey: str = Field(..., max_length=100)  # Date: YYYY-MM-DD
    RowKey: str = Field(..., max_length=200)  # Request ID
    pr_id: int = Field(..., gt=0, lt=2147483647)
    repository: str = Field(..., max_length=500)
    project: str = Field(..., max_length=500)
    event_type: str = Field(..., max_length=100)  # "pr.created", "pr.updated", etc.
    first_processed_at: datetime
    last_seen_at: datetime
    processing_count: int = Field(default=1, ge=1, lt=1000)
    result_summary: str = Field(..., max_length=1000)  # Brief summary of review result

    @field_validator("PartitionKey")
    @classmethod
    def validate_partition_key(cls, v: str) -> str:
        """Validate partition key is a valid date format."""
        import re

        if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            raise ValueError("PartitionKey must be in YYYY-MM-DD format")
        return v

    @classmethod
    def create_request_id(
        cls,
        pr_id: int,
        repository: str,
        event_type: str,
        source_commit_id: Optional[str] = None,
    ) -> str:
        """
        Generate deterministic request ID.

        v2.6.12: Removed event_type from hash to prevent duplicate reviews
        when both "created" and "updated" webhooks fire simultaneously.
        Idempotency is now based on pr_id + repository + source_commit_id.

        Args:
            pr_id: Pull request ID
            repository: Repository name
            event_type: Webhook event type (kept for logging, not used in hash)
            source_commit_id: Latest commit ID (required for proper deduplication)

        Returns:
            Unique request ID string
        """
        # Create stable hash of request parameters
        # v2.6.12: Exclude event_type to deduplicate across created/updated webhooks
        parts = [str(pr_id), repository]
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
        result_summary: str = "pending",
    ) -> "IdempotencyEntity":
        """Create IdempotencyEntity from PR event data."""
        now = datetime.now(timezone.utc)
        request_id = cls.create_request_id(
            pr_id, repository, event_type, source_commit_id
        )

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
            result_summary=result_summary,
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
            "result_summary": self.result_summary,
        }


class CacheEntity(BaseModel):
    """
    Caches AI review responses to reduce costs for identical diffs.

    Storage Strategy:
    - PartitionKey: Repository name (for efficient cleanup)
    - RowKey: Content hash (SHA256 of diff content)
    - TTL: 7 days
    """

    PartitionKey: str = Field(..., max_length=500)  # Repository name
    RowKey: str = Field(..., max_length=100)  # Content hash (SHA256)
    diff_hash: str = Field(..., max_length=100)
    file_path: str = Field(..., max_length=2000)
    file_type: str = Field(..., max_length=50)
    review_result_json: str = Field(
        ..., max_length=1000000
    )  # Serialized ReviewResult (1MB limit)
    tokens_used: int = Field(..., ge=0, lt=10000000)
    estimated_cost: float = Field(..., ge=0, lt=10000.0)
    model_used: str = Field(..., max_length=200)
    created_at: datetime
    last_accessed_at: datetime
    hit_count: int = Field(default=1, ge=1, lt=1000000)
    expires_at: datetime  # 7 days from creation

    @field_validator("review_result_json")
    @classmethod
    def validate_review_json(cls, v: str) -> str:
        """Validate that review_result_json contains valid JSON."""
        try:
            json.loads(v)
            return v
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in review_result_json: {e}")

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
        ttl_days: int = 7,
    ) -> "CacheEntity":
        """Create CacheEntity from review result."""
        now = datetime.now(timezone.utc)
        content_hash = cls.create_content_hash(diff_content, file_path)

        # Serialize review result
        review_json = (
            review_result.model_dump_json()
            if hasattr(review_result, "model_dump_json")
            else json.dumps(review_result)
        )

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
            expires_at=now + timedelta(days=ttl_days),
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
            "expires_at": self.expires_at,
        }


class CircuitBreakerState(BaseModel):
    """
    Tracks circuit breaker state for external service.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Too many failures, requests fail fast
    - HALF_OPEN: Testing if service recovered
    """

    service_name: str = Field(..., max_length=200)
    state: str = Field(..., max_length=20)  # "CLOSED", "OPEN", "HALF_OPEN"
    failure_count: int = Field(default=0, ge=0, lt=10000)
    success_count: int = Field(default=0, ge=0, lt=10000)
    last_failure_time: Optional[datetime] = None
    last_state_change: datetime
    next_retry_time: Optional[datetime] = None

    @field_validator("state")
    @classmethod
    def validate_state(cls, v: str) -> str:
        """Validate circuit breaker state is valid."""
        valid_states = ["CLOSED", "OPEN", "HALF_OPEN"]
        if v not in valid_states:
            raise ValueError(f"state must be one of {valid_states}")
        return v

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

    def record_failure(
        self,
        failure_threshold: int = DEFAULT_CIRCUIT_BREAKER_FAILURE_THRESHOLD,
        timeout_seconds: int = DEFAULT_CIRCUIT_BREAKER_TIMEOUT_SECONDS,
    ) -> None:
        """Record failed request and potentially open circuit."""
        now = datetime.now(timezone.utc)
        self.failure_count += 1
        self.last_failure_time = now

        # HALF_OPEN -> OPEN: Any failure during recovery test reopens circuit
        if self.state == "HALF_OPEN":
            self.state = "OPEN"
            self.last_state_change = now
            self.next_retry_time = now + timedelta(seconds=timeout_seconds)
            self.success_count = 0  # Reset success counter
        # CLOSED -> OPEN: Need threshold failures to open
        elif self.failure_count >= failure_threshold and self.state == "CLOSED":
            self.state = "OPEN"
            self.last_state_change = now
            self.next_retry_time = now + timedelta(seconds=timeout_seconds)

    def should_allow_request(self) -> bool:
        """
        Check if request should be allowed through.

        IMPORTANT: This method does NOT modify state. State transitions
        happen under lock protection in CircuitBreaker.call().

        THREAD SAFETY NOTE (v2.5.8):
        This is a read-only check that may be subject to TOCTOU (time-of-check
        to-time-of-use) races. The calling code MUST protect state transitions
        with proper synchronization (locks/mutexes). Do not rely on this method
        alone for thread safety.

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
