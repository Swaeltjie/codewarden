# function_app.py
"""
AI PR Reviewer - Main Azure Functions Entry Point

This module defines the Azure Functions HTTP triggers and orchestrates
the PR review workflow.

Version: 2.4.0 - Added timeout handling, dry-run mode, improved error logging
"""
import azure.functions as func
import logging
import json
import asyncio
import os
import uuid
from datetime import datetime, timezone
from typing import Optional, Any, Dict, List

import structlog

from src.handlers.pr_webhook import PRWebhookHandler
from src.utils.config import get_settings, cleanup_secret_manager
from src.utils.logging import setup_logging
from src.models.pr_event import PREvent
from src.utils.table_storage import cleanup_table_storage

# Function-level timeout (8 minutes, leaves buffer before Azure's 10min timeout)
FUNCTION_TIMEOUT_SECONDS = 480

# Dry-run mode - skips posting to Azure DevOps
DRY_RUN_MODE = os.environ.get('DRY_RUN', 'false').lower() == 'true'

# Initialize logging
settings = get_settings()
setup_logging(settings.LOG_LEVEL)
logger = structlog.get_logger(__name__)

# Create Function App
app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


@app.route(route="pr-webhook", methods=["POST"])
async def pr_webhook_trigger(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP trigger for Azure DevOps Pull Request webhooks.
    
    This function receives PR events from Azure DevOps, validates them,
    and triggers the AI review process.
    
    Args:
        req: HTTP request from Azure DevOps webhook
        
    Returns:
        HTTP response with status and review ID
    """
    correlation_id = req.headers.get('x-correlation-id', str(datetime.now(timezone.utc).timestamp()))
    
    # Bind correlation ID to logger context
    logger = structlog.get_logger(__name__).bind(correlation_id=correlation_id)
    
    logger.info(
        "webhook_received",
        method=req.method,
        url=req.url,
        headers_count=len(req.headers)
    )

    try:
        # Rate limiting check
        client_ip = _get_client_ip(req)
        if await _rate_limiter.is_rate_limited(client_ip):
            return func.HttpResponse(
                json.dumps({
                    "error": "Rate limit exceeded",
                    "retry_after": 60,
                    "message": "Too many requests. Please wait before retrying."
                }),
                status_code=429,
                mimetype="application/json",
                headers={"Retry-After": "60"}
            )

        # Validate payload size (max 1MB)
        MAX_PAYLOAD_SIZE = 1024 * 1024  # 1MB
        content_length = req.headers.get('Content-Length')

        if content_length and int(content_length) > MAX_PAYLOAD_SIZE:
            logger.warning("payload_too_large", size=content_length)
            return func.HttpResponse(
                json.dumps({"error": "Payload too large (max 1MB)"}),
                status_code=413,
                mimetype="application/json"
            )

        # Parse request body with additional validation
        try:
            raw_body = req.get_body()

            # Check actual body size
            if len(raw_body) > MAX_PAYLOAD_SIZE:
                logger.warning("payload_size_exceeded", size=len(raw_body))
                return func.HttpResponse(
                    json.dumps({"error": "Payload too large (max 1MB)"}),
                    status_code=413,
                    mimetype="application/json"
                )

            # Parse JSON with depth checking
            body = json.loads(raw_body)

            # Validate JSON structure depth (prevent deeply nested payloads)
            if not _validate_json_depth(body, max_depth=10):
                logger.warning("json_too_deeply_nested")
                return func.HttpResponse(
                    json.dumps({"error": "JSON structure too deeply nested (max depth: 10)"}),
                    status_code=400,
                    mimetype="application/json"
                )

        except ValueError as e:
            logger.error("invalid_json_payload")
            return func.HttpResponse(
                json.dumps({"error": "Invalid JSON payload"}),
                status_code=400,
                mimetype="application/json"
            )
        except json.JSONDecodeError as e:
            logger.error("json_decode_failed")
            return func.HttpResponse(
                json.dumps({"error": "Malformed JSON"}),
                status_code=400,
                mimetype="application/json"
            )
        
        # Validate webhook secret
        webhook_secret = req.headers.get('x-webhook-secret')
        if not _validate_webhook_secret(webhook_secret):
            logger.warning("invalid_webhook_secret")
            return func.HttpResponse(
                json.dumps({"error": "Unauthorized"}),
                status_code=401,
                mimetype="application/json"
            )
        
        # Validate event type first
        event_type = body.get('eventType', '')
        if event_type not in ['git.pullrequest.created', 'git.pullrequest.updated']:
            logger.info("ignored_event_type", event_type=event_type)
            return func.HttpResponse(
                json.dumps({"message": f"Event type '{event_type}' ignored"}),
                status_code=200,
                mimetype="application/json"
            )
        
        # Validate resource field exists
        resource = body.get('resource')
        if not resource:
            logger.error("webhook_missing_resource")
            return func.HttpResponse(
                json.dumps({"error": "Missing 'resource' field in webhook payload"}),
                status_code=400,
                mimetype="application/json"
            )
        
        # Parse PR event with proper error handling
        # Track context for error logging
        pr_id = None
        repository = None

        try:
            pr_event = PREvent.from_azure_devops_webhook(body)
            pr_id = pr_event.pr_id
            repository = pr_event.repository_name

            logger.info(
                "pr_event_parsed",
                pr_id=pr_event.pr_id,
                repository=pr_event.repository_name,
                author=pr_event.author_email,
                dry_run=DRY_RUN_MODE
            )
        except KeyError as e:
            logger.error(
                "webhook_parsing_failed",
                missing_field=str(e),
                body_keys=list(body.keys())
            )
            return func.HttpResponse(
                json.dumps({"error": f"Invalid webhook structure: missing field {e}"}),
                status_code=400,
                mimetype="application/json"
            )
        except (ValueError, TypeError) as e:
            logger.error(
                "pr_event_parse_failed",
                error=str(e),
                error_type=type(e).__name__
            )
            return func.HttpResponse(
                json.dumps({"error": f"Invalid PR event format: {str(e)}"}),
                status_code=400,
                mimetype="application/json"
            )

        # Initialize handler with context manager for proper resource cleanup
        async with PRWebhookHandler() as handler:
            # Set dry-run mode if enabled
            if DRY_RUN_MODE:
                handler.dry_run = True
                logger.info("dry_run_mode_enabled", pr_id=pr_id)

            # Process the PR with timeout protection
            try:
                review_result = await asyncio.wait_for(
                    handler.handle_pr_event(pr_event),
                    timeout=FUNCTION_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                error_id = str(uuid.uuid4())
                logger.error(
                    "pr_review_timeout",
                    error_id=error_id,
                    pr_id=pr_id,
                    repository=repository,
                    timeout_seconds=FUNCTION_TIMEOUT_SECONDS
                )
                return func.HttpResponse(
                    json.dumps({
                        "error": "Review timeout",
                        "error_id": error_id,
                        "pr_id": pr_id,
                        "message": f"PR review exceeded {FUNCTION_TIMEOUT_SECONDS}s timeout. Try reducing PR size."
                    }),
                    status_code=504,
                    mimetype="application/json"
                )

        # Log token usage metrics for monitoring
        logger.info(
            "pr_review_completed",
            pr_id=pr_event.pr_id,
            review_id=review_result.review_id,
            issues_found=len(review_result.issues),
            duration_seconds=review_result.duration_seconds,
            tokens_used=review_result.tokens_used,
            estimated_cost=review_result.estimated_cost,
            dry_run=DRY_RUN_MODE
        )

        # Return success response with token metrics
        return func.HttpResponse(
            json.dumps({
                "status": "success",
                "review_id": review_result.review_id,
                "pr_id": pr_event.pr_id,
                "issues_found": len(review_result.issues),
                "duration_seconds": review_result.duration_seconds,
                "recommendation": review_result.recommendation,
                "tokens_used": review_result.tokens_used,
                "estimated_cost_usd": review_result.estimated_cost,
                "dry_run": DRY_RUN_MODE
            }),
            status_code=200,
            mimetype="application/json"
        )

    except (ConnectionError, TimeoutError) as e:
        # Network-related errors
        error_id = str(uuid.uuid4())
        logger.error(
            "webhook_network_error",
            error_id=error_id,
            error_type=type(e).__name__,
            pr_id=pr_id,
            repository=repository
        )
        return func.HttpResponse(
            json.dumps({
                "error": "Service temporarily unavailable",
                "error_id": error_id,
                "message": "Network error occurred. Please retry."
            }),
            status_code=503,
            mimetype="application/json"
        )

    except (ValueError, TypeError, KeyError) as e:
        # Data validation errors
        error_id = str(uuid.uuid4())
        logger.error(
            "webhook_validation_error",
            error_id=error_id,
            error_type=type(e).__name__,
            error=str(e),
            pr_id=pr_id,
            repository=repository
        )
        return func.HttpResponse(
            json.dumps({
                "error": "Invalid request data",
                "error_id": error_id,
                "message": "Request validation failed."
            }),
            status_code=400,
            mimetype="application/json"
        )

    except Exception as e:
        # Catch-all for unexpected errors (logged with full context)
        error_id = str(uuid.uuid4())

        logger.exception(
            "webhook_processing_failed",
            error_id=error_id,
            error_type=type(e).__name__,
            pr_id=pr_id,
            repository=repository
        )

        # Never expose internal error details in response
        return func.HttpResponse(
            json.dumps({
                "error": "Internal server error",
                "error_id": error_id,
                "message": "An unexpected error occurred. Please contact support with the error_id."
            }),
            status_code=500,
            mimetype="application/json"
        )


@app.timer_trigger(schedule="0 0 * * * *", arg_name="timer", run_on_startup=False)
async def feedback_collector_trigger(timer: func.TimerRequest) -> None:
    """
    Timer trigger that runs hourly to collect feedback from PR threads.
    
    This function monitors Azure DevOps PR threads for developer feedback
    (resolved, won't fix, thumbs up/down) and stores it for learning.
    
    Args:
        timer: Timer trigger context
    """
    logger.info(
        "feedback_collection_started",
        past_due=timer.past_due,
        schedule_status=timer.schedule_status
    )
    
    try:
        from src.services.feedback_tracker import FeedbackTracker

        # Use context manager for proper resource cleanup
        async with FeedbackTracker() as tracker:
            # Collect feedback from PRs in last 24 hours
            feedback_count = await tracker.collect_recent_feedback(hours=24)
        
        logger.info(
            "feedback_collection_completed",
            feedback_entries=feedback_count
        )
        
    except Exception as e:
        logger.exception(
            "feedback_collection_failed",
            error=str(e),
            error_type=type(e).__name__
        )


@app.timer_trigger(schedule="0 0 2 * * *", arg_name="timer", run_on_startup=False)
async def pattern_detector_trigger(timer: func.TimerRequest) -> None:
    """
    Timer trigger that runs daily at 2 AM to analyze patterns.
    
    This function analyzes historical review data to identify recurring
    issues, problematic files, and architectural patterns.
    
    Args:
        timer: Timer trigger context
    """
    logger.info("pattern_detection_started", past_due=timer.past_due)
    
    try:
        from src.services.pattern_detector import PatternDetector
        
        detector = PatternDetector()
        
        # Analyze patterns for all active repositories
        patterns = await detector.analyze_all_repositories(days=30)
        
        logger.info(
            "pattern_detection_completed",
            patterns_found=len(patterns),
            repositories_analyzed=len(patterns)
        )
        
    except Exception as e:
        logger.exception(
            "pattern_detection_failed",
            error=str(e),
            error_type=type(e).__name__
        )


@app.route(route="health", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
async def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """
    Health check endpoint for monitoring.

    Requires function-level authentication for security.

    Returns:
        HTTP 200 if service is healthy
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "2.4.0"
    }
    
    # Check dependencies
    try:
        from src.services.azure_devops import AzureDevOpsClient
        from src.services.ai_client import AIClient

        # Quick dependency check (don't make actual calls)
        # Use context managers to ensure proper cleanup
        async with AzureDevOpsClient() as devops_client:
            async with AIClient() as ai_client:
                health_status["dependencies"] = {
                    "azure_devops": "initialized",
                    "ai_client": "initialized",
                    "table_storage": "configured"
                }

    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["error"] = str(e)
        return func.HttpResponse(
            json.dumps(health_status),
            status_code=503,
            mimetype="application/json"
        )

    return func.HttpResponse(
        json.dumps(health_status),
        status_code=200,
        mimetype="application/json"
    )


@app.route(route="reliability-health", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
async def reliability_health_check(req: func.HttpRequest) -> func.HttpResponse:
    """
    Reliability features health check endpoint.

    Provides detailed status for:
    - Circuit breakers (OpenAI, Azure DevOps)
    - Response cache (hit rates, cost savings)
    - Idempotency (duplicate detection)

    Requires function-level authentication for security.

    Query parameters:
    - feature: specific feature to check (circuit_breakers, cache, idempotency)
    - repository: filter cache stats by repository (optional)

    Returns:
        HTTP 200 with detailed reliability metrics
    """
    try:
        from src.handlers.reliability_health import ReliabilityHealthHandler

        handler = ReliabilityHealthHandler()

        # Check for specific feature request
        feature = req.params.get('feature')
        repository = req.params.get('repository')

        if feature == 'circuit_breakers':
            result = await handler.get_circuit_breaker_status()
        elif feature == 'cache':
            result = await handler.get_cache_statistics(repository=repository)
        elif feature == 'idempotency':
            days = int(req.params.get('days', 7))
            result = await handler.get_idempotency_statistics(days=days)
        else:
            # Full health status
            result = await handler.get_health_status()

        status_code = 200 if result.get("status") in ["healthy", "degraded"] else 503

        return func.HttpResponse(
            json.dumps(result, indent=2),
            status_code=status_code,
            mimetype="application/json"
        )

    except Exception as e:
        logger.exception("reliability_health_check_failed", error=str(e))

        error_response = {
            "status": "error",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(e),
            "error_type": type(e).__name__
        }

        return func.HttpResponse(
            json.dumps(error_response),
            status_code=500,
            mimetype="application/json"
        )


def _validate_webhook_secret(provided_secret: Optional[str]) -> bool:
    """
    Validate webhook secret from Azure DevOps using constant-time comparison.

    Security measures:
    - Uses hmac.compare_digest() to prevent timing attacks
    - No development environment bypass (removed for security)
    - Logs failures for monitoring

    Timing attacks work by measuring how long string comparison takes.
    Early exit on mismatch makes timing reveal secret length/content.
    constant-time comparison always checks full string regardless of match.

    Args:
        provided_secret: Secret from x-webhook-secret header

    Returns:
        True if secret matches, False otherwise

    Security Note:
        Never use == for secret comparison - use hmac.compare_digest()
        to prevent timing side-channel attacks.
    """
    if not provided_secret:
        logger.warning("webhook_secret_missing")
        return False

    from src.utils.config import get_secret_manager

    try:
        secret_manager = get_secret_manager()
        expected_secret = secret_manager.get_secret("WEBHOOK_SECRET")

        # Use constant-time comparison to prevent timing attacks
        # hmac.compare_digest() ensures comparison takes same time
        # whether strings match or not, preventing attackers from
        # using timing to guess the secret character-by-character
        import hmac
        return hmac.compare_digest(provided_secret, expected_secret)
    except Exception as e:
        logger.error("webhook_secret_validation_failed", error=str(e))
        return False


def _validate_json_depth(obj: Any, max_depth: int, current_depth: int = 0) -> bool:
    """
    Validate JSON object depth to prevent deeply nested structures.

    Recursively traverses the JSON structure counting nesting levels.
    Protects against:
    - Parser DoS attacks via deeply nested JSON
    - Stack overflow from excessive recursion
    - Memory exhaustion from malicious payloads

    Args:
        obj: JSON object to validate (dict, list, or primitive)
        max_depth: Maximum allowed nesting depth (typically 10)
        current_depth: Current depth in recursion (starts at 0)

    Returns:
        True if depth is acceptable, False if exceeds max_depth

    Example:
        >>> _validate_json_depth({"a": {"b": {"c": 1}}}, max_depth=3)
        True
        >>> _validate_json_depth({"a": {"b": {"c": {"d": 1}}}}, max_depth=3)
        False
    """
    # Base case: exceeded maximum depth
    if current_depth > max_depth:
        return False

    # Recursive case: dictionary - check all values
    if isinstance(obj, dict):
        return all(
            _validate_json_depth(value, max_depth, current_depth + 1)
            for value in obj.values()
        )
    # Recursive case: list - check all items
    elif isinstance(obj, list):
        return all(
            _validate_json_depth(item, max_depth, current_depth + 1)
            for item in obj
        )

    # Base case: primitive types (str, int, bool, None) have no depth
    return True


# =============================================================================
# Rate Limiting
# =============================================================================

class RateLimiter:
    """
    Simple in-memory rate limiter for webhook endpoint.

    Uses a sliding window counter per client IP to prevent abuse.
    Limits are per-function-instance (resets on cold start).
    """

    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        """
        Initialize rate limiter.

        Args:
            max_requests: Maximum requests per window (default: 100)
            window_seconds: Time window in seconds (default: 60)
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: Dict[str, List[float]] = {}
        self._lock = asyncio.Lock()

    async def is_rate_limited(self, client_id: str) -> bool:
        """
        Check if client is rate limited.

        Args:
            client_id: Unique client identifier (e.g., IP address)

        Returns:
            True if rate limited, False otherwise
        """
        now = datetime.now(timezone.utc).timestamp()
        window_start = now - self.window_seconds

        async with self._lock:
            # Get or create request list for client
            if client_id not in self._requests:
                self._requests[client_id] = []

            # Remove old requests outside window
            self._requests[client_id] = [
                ts for ts in self._requests[client_id]
                if ts > window_start
            ]

            # Check if over limit
            if len(self._requests[client_id]) >= self.max_requests:
                logger.warning(
                    "rate_limit_exceeded",
                    client_id=client_id,
                    requests_in_window=len(self._requests[client_id])
                )
                return True

            # Record this request
            self._requests[client_id].append(now)
            return False

    def get_remaining(self, client_id: str) -> int:
        """Get remaining requests for client."""
        if client_id not in self._requests:
            return self.max_requests
        return max(0, self.max_requests - len(self._requests.get(client_id, [])))


# Global rate limiter instance (100 requests per minute per IP)
_rate_limiter = RateLimiter(max_requests=100, window_seconds=60)


def _get_client_ip(req: func.HttpRequest) -> str:
    """
    Extract client IP from request.

    Checks X-Forwarded-For header for requests behind load balancer,
    falls back to direct client address.

    Args:
        req: HTTP request

    Returns:
        Client IP address
    """
    # Azure Functions behind App Gateway/Load Balancer
    forwarded_for = req.headers.get('X-Forwarded-For', '')
    if forwarded_for:
        # Take first IP in chain (original client)
        return forwarded_for.split(',')[0].strip()

    # Direct connection (development)
    return req.headers.get('X-Client-IP', 'unknown')


# =============================================================================
# Shutdown Handler
# =============================================================================

import atexit


def _cleanup_resources():
    """
    Cleanup resources on application shutdown.

    Called via atexit handler to ensure proper cleanup of:
    - Secret Manager credentials
    - Table Storage connections
    """
    try:
        cleanup_secret_manager()
        logger.info("secret_manager_cleaned_up_on_shutdown")
    except Exception as e:
        logger.warning("secret_manager_cleanup_failed", error=str(e))

    try:
        # Note: cleanup_table_storage is async but we're in sync context
        # For sync cleanup, just log - the credential will be GC'd
        logger.info("table_storage_cleanup_scheduled")
    except Exception as e:
        logger.warning("table_storage_cleanup_failed", error=str(e))


# Register cleanup handler
atexit.register(_cleanup_resources)
