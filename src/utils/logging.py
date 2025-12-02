# src/utils/logging.py
"""
Logging Configuration for Datadog

Configures structured logging with Datadog integration using ddtrace.

Version: 2.5.7 - Added get_logger() convenience function for centralized imports
"""
import logging
import structlog
from ddtrace import tracer, patch_all
import sys


def setup_logging(log_level: str = "INFO"):
    """
    Configure structured logging with Datadog integration.

    Uses structlog for structured logging (JSON format) and ddtrace for
    automatic instrumentation and APM tracing.

    Key features:
    - JSON output for easy parsing by Datadog
    - Automatic correlation IDs
    - Context binding (pr_id, repository, etc.)
    - Integrates with Datadog APM via ddtrace

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)

    Raises:
        ValueError: If log_level is not a valid logging level
    """
    # Validate log level before use
    valid_levels = {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}
    log_level_upper = log_level.upper()

    if log_level_upper not in valid_levels:
        raise ValueError(
            f"Invalid log level: {log_level}. "
            f"Must be one of: {', '.join(sorted(valid_levels))}"
        )

    # Enable Datadog auto-instrumentation
    # This automatically traces HTTP requests, database calls, etc.
    patch_all()

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

    # Remove default handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add stdout handler (Azure Functions reads from stdout)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, log_level_upper))
    
    # Simple format for standard logging (structlog handles formatting)
    handler.setFormatter(logging.Formatter('%(message)s'))
    
    root_logger.addHandler(handler)
    
    # Log configuration success
    logger = structlog.get_logger(__name__)
    logger.info(
        "logging_configured",
        log_level=log_level_upper,
        datadog_enabled=True,
        structured=True
    )


def get_correlation_id_from_context() -> str:
    """
    Get current correlation ID from Datadog trace context.

    Returns:
        Correlation ID (trace ID from Datadog)
    """
    span = tracer.current_span()
    if span:
        return str(span.trace_id)
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
