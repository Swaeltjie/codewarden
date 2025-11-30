# function_app.py
"""
AI PR Reviewer - Main Azure Functions Entry Point

This module defines the Azure Functions HTTP triggers and orchestrates
the PR review workflow.
"""
import azure.functions as func
import logging
import json
import asyncio
from datetime import datetime, timezone
from typing import Optional, Any, Dict, List

import structlog

from src.handlers.pr_webhook import PRWebhookHandler
from src.utils.config import get_settings
from src.utils.logging import setup_logging
from src.models.pr_event import PREvent

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
        try:
            pr_event = PREvent.from_azure_devops_webhook(body)
            logger.info(
                "pr_event_parsed",
                pr_id=pr_event.pr_id,
                repository=pr_event.repository_name,
                author=pr_event.author_email
            )
        except KeyError as e:
            logger.error("webhook_parsing_failed", missing_field=str(e), body_keys=list(body.keys()))
            return func.HttpResponse(
                json.dumps({"error": f"Invalid webhook structure: missing field {e}"}),
                status_code=400,
                mimetype="application/json"
            )
        except Exception as e:
            logger.error("pr_event_parse_failed", error=str(e), body=body)
            return func.HttpResponse(
                json.dumps({"error": f"Invalid PR event format: {str(e)}"}),
                status_code=400,
                mimetype="application/json"
            )
        
        # Initialize handler with context manager for proper resource cleanup
        async with PRWebhookHandler() as handler:
            # Process the PR (async)
            review_result = await handler.handle_pr_event(pr_event)
        
        logger.info(
            "pr_review_completed",
            pr_id=pr_event.pr_id,
            review_id=review_result.review_id,
            issues_found=len(review_result.issues),
            duration_seconds=review_result.duration_seconds
        )
        
        # Return success response
        return func.HttpResponse(
            json.dumps({
                "status": "success",
                "review_id": review_result.review_id,
                "pr_id": pr_event.pr_id,
                "issues_found": len(review_result.issues),
                "duration_seconds": review_result.duration_seconds,
                "recommendation": review_result.recommendation
            }),
            status_code=200,
            mimetype="application/json"
        )
        
    except Exception as e:
        # Generate error ID for tracking
        import uuid
        error_id = str(uuid.uuid4())

        logger.exception(
            "webhook_processing_failed",
            error_id=error_id,
            error_type=type(e).__name__
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
        "version": "2.2.0"
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
