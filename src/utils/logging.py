# src/utils/logging.py
"""
Logging Configuration for Datadog

Configures structured logging with Datadog integration using ddtrace.

Version: 2.7.6 - Added sensitive data sanitization, context cleanup
"""
import logging
import structlog
import sys
import threading
from typing import Optional

from src.utils.constants import LOG_FIELD_MAX_LENGTH

# Explicit public API
__all__ = [
    "setup_logging",
    "get_logger",
    "get_correlation_id_from_context",
    "is_logging_configured",
    "clear_logging_context",
]

# Module-level state to track configuration (thread-safe)
_logging_configured = False
_logging_lock = threading.Lock()
_ddtrace_available = False

# Sensitive field names to redact from logs
_SENSITIVE_KEYS = {
    "password",
    "passwd",
    "pwd",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "api_key",
    "apikey",
    "pat",
    "credential",
    "credentials",
    "auth",
    "authorization",
    "key",
    "private_key",
    "connection_string",
    "connectionstring",
}

# Try to import ddtrace - graceful degradation if not available
try:
    from ddtrace import tracer, patch_all

    _ddtrace_available = True
except ImportError:
    tracer = None
    patch_all = None


def _sanitize_sensitive_data(
    logger: structlog.BoundLogger, method_name: str, event_dict: dict
) -> dict:
    """
    Sanitize sensitive fields before logging.

    Replaces values of sensitive keys with '***REDACTED***'.
    """
    for key in list(event_dict.keys()):
        if (
            key.lower() in _SENSITIVE_KEYS
            or "secret" in key.lower()
            or "password" in key.lower()
        ):
            event_dict[key] = "***REDACTED***"
    return event_dict


def _sanitize_log_values(
    logger: structlog.BoundLogger, method_name: str, event_dict: dict
) -> dict:
    """
    Sanitize and truncate log field values.

    - Removes null bytes and control characters
    - Truncates excessively long values
    """
    for key, value in list(event_dict.items()):
        if isinstance(value, str):
            # Remove null bytes (log injection vector)
            if "\x00" in value:
                value = value.replace("\x00", "")
            # Remove other control characters except newlines/tabs
            value = "".join(
                char for char in value if char.isprintable() or char in "\n\t"
            )
            # Truncate long values
            if len(value) > LOG_FIELD_MAX_LENGTH:
                value = value[:LOG_FIELD_MAX_LENGTH] + "...[truncated]"
            event_dict[key] = value
    return event_dict


def is_logging_configured() -> bool:
    """
    Check if logging has been configured.

    Returns:
        True if setup_logging() has been called successfully
    """
    return _logging_configured


def clear_logging_context() -> None:
    """
    Clear all bound context variables.

    Should be called at the start of each request to prevent
    context leakage between requests in long-lived function instances.

    Example:
        from src.utils.logging import clear_logging_context

        def handle_request():
            clear_logging_context()  # Start fresh
            # ... process request ...
    """
    structlog.contextvars.clear_contextvars()


def setup_logging(log_level: str = "INFO", force: bool = False) -> None:
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
    - Sensitive data sanitization (passwords, tokens, etc.)
    - Log value truncation to prevent bloat

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        force: If True, reconfigure even if already configured

    Raises:
        ValueError: If log_level is not a valid logging level
    """
    global _logging_configured

    # Thread-safe idempotency check
    with _logging_lock:
        if _logging_configured and not force:
            return

        # Validate log level before use
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
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
            except Exception as e:
                # Log the error but don't fail logging setup
                print(
                    f"WARNING: ddtrace patching failed: {type(e).__name__}: {e}",
                    file=sys.stderr,
                )

        # Configure structlog processors
        # IMPORTANT: Order matters! Processors run sequentially:
        # 1. Merge context variables first (adds pr_id, correlation_id, etc.)
        # 2. Add log level
        # 3. Add timestamp
        # 4. Sanitize values (before sensitive data check)
        # 5. Sanitize sensitive data (before JSON rendering)
        # 6. Render as JSON (must be last)
        processors = [
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _sanitize_log_values,
            _sanitize_sensitive_data,
            structlog.processors.JSONRenderer(),
        ]

        # Configure structlog
        structlog.configure(
            processors=processors,
            wrapper_class=structlog.make_filtering_bound_logger(
                logging.getLevelName(log_level_upper)
            ),
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
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
        handler.setFormatter(logging.Formatter("%(message)s"))

        root_logger.addHandler(handler)

        # Mark as configured
        _logging_configured = True

    # Log configuration success (outside lock to prevent deadlock)
    logger = structlog.get_logger(__name__)
    logger.info(
        "logging_configured",
        log_level=log_level_upper,
        datadog_enabled=_ddtrace_available,
        structured=True,
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


def get_logger(name: str) -> structlog.BoundLoggerBase:
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
