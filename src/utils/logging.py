# src/utils/logging.py
"""
Logging Configuration for Datadog

Configures structured logging with Datadog integration using ddtrace.

Version: 2.5.10 - Improved robustness: idempotency, exception handling, explicit API
"""
import logging
import structlog
import sys
from typing import Optional

# Explicit public API
__all__ = ['setup_logging', 'get_logger', 'get_correlation_id_from_context', 'is_logging_configured']

# Module-level state to track configuration
_logging_configured = False
_ddtrace_available = False

# Try to import ddtrace - graceful degradation if not available
try:
    from ddtrace import tracer, patch_all
    _ddtrace_available = True
except ImportError:
    tracer = None
    patch_all = None


def is_logging_configured() -> bool:
    """
    Check if logging has been configured.

    Returns:
        True if setup_logging() has been called successfully
    """
    return _logging_configured


def setup_logging(log_level: str = "INFO", force: bool = False):
    """
    Configure structured logging with Datadog integration.

    Uses structlog for structured logging (JSON format) and ddtrace for
    automatic instrumentation and APM tracing.

    Key features:
    - JSON output for easy parsing by Datadog
    - Automatic correlation IDs
    - Context binding (pr_id, repository, etc.)
    - Integrates with Datadog APM via ddtrace
    - Idempotent - safe to call multiple times

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        force: If True, reconfigure even if already configured

    Raises:
        ValueError: If log_level is not a valid logging level
    """
    global _logging_configured

    # Idempotency check - don't reconfigure unless forced
    if _logging_configured and not force:
        return

    # Validate log level before use
    valid_levels = {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}
    log_level_upper = log_level.upper()

    if log_level_upper not in valid_levels:
        raise ValueError(
            f"Invalid log level: {log_level}. "
            f"Must be one of: {', '.join(sorted(valid_levels))}"
        )

    # Enable Datadog auto-instrumentation if available
    # Graceful degradation if ddtrace is not installed
    if _ddtrace_available and patch_all is not None:
        try:
            patch_all()
        except Exception:
            # Don't fail logging setup if ddtrace patching fails
            pass

    # Configure structlog processors
    processors = [
        # Add contextvars (correlation_id, pr_id, etc.)
        structlog.contextvars.merge_contextvars,

        # Add log level to each log entry
        structlog.processors.add_log_level,

        # Add timestamp in ISO format
        structlog.processors.TimeStamper(fmt="iso"),

        # Render as JSON (Datadog-friendly)
        structlog.processors.JSONRenderer()
    ]

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(log_level_upper)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True
    )

    # Configure root logger for standard library logging
    # (some libraries use standard logging instead of structlog)
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level_upper))

    # Remove default handlers (prevents duplicate logs)
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add stdout handler (Azure Functions reads from stdout)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, log_level_upper))

    # Simple format for standard logging (structlog handles formatting)
    handler.setFormatter(logging.Formatter('%(message)s'))

    root_logger.addHandler(handler)

    # Mark as configured
    _logging_configured = True

    # Log configuration success
    logger = structlog.get_logger(__name__)
    logger.info(
        "logging_configured",
        log_level=log_level_upper,
        datadog_enabled=_ddtrace_available,
        structured=True
    )


def get_correlation_id_from_context() -> str:
    """
    Get current correlation ID from Datadog trace context.

    Returns:
        Correlation ID (trace ID from Datadog), or "no-trace" if unavailable
    """
    if not _ddtrace_available or tracer is None:
        return "no-trace"

    try:
        span = tracer.current_span()
        if span:
            return str(span.trace_id)
    except Exception:
        # Don't fail if trace context retrieval fails
        pass

    return "no-trace"


def get_logger(name: str):
    """
    Get a configured structlog logger.

    Convenience function for centralized logger imports.
    Modules should use this instead of importing structlog directly.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured structlog BoundLogger instance

    Example:
        from src.utils.logging import get_logger
        logger = get_logger(__name__)
        logger.info("event_occurred", key="value")
    """
    return structlog.get_logger(name)
