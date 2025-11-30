# src/utils/logging.py
"""
Logging Configuration for Datadog

Configures structured logging with Datadog integration using ddtrace.

Version: 1.0.0
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
    """
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
            logging.getLevelName(log_level)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True
    )
    
    # Configure root logger for standard library logging
    # (some libraries use standard logging instead of structlog)
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level))
    
    # Remove default handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Add stdout handler (Azure Functions reads from stdout)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, log_level))
    
    # Simple format for standard logging (structlog handles formatting)
    handler.setFormatter(logging.Formatter('%(message)s'))
    
    root_logger.addHandler(handler)
    
    # Log configuration success
    logger = structlog.get_logger(__name__)
    logger.info(
        "logging_configured",
        log_level=log_level,
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
