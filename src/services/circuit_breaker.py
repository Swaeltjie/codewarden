# src/services/circuit_breaker.py
"""
Circuit Breaker Pattern

Prevents cascading failures when external services are down.

Version: 2.6.36 - Lazy lock initialization to avoid event loop binding
"""
from typing import Callable, Any, Optional, Dict, TypeVar, ParamSpec
from datetime import datetime, timezone, timedelta
import asyncio
from functools import wraps

from src.models.reliability import CircuitBreakerState
from src.utils.logging import get_logger
from src.utils.constants import (
    CIRCUIT_BREAKER_LOCK_TIMEOUT_SECONDS,
    DEFAULT_CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    DEFAULT_CIRCUIT_BREAKER_TIMEOUT_SECONDS,
    DEFAULT_CIRCUIT_BREAKER_SUCCESS_THRESHOLD,
)

# Alias for backward compatibility
LOCK_TIMEOUT_SECONDS = CIRCUIT_BREAKER_LOCK_TIMEOUT_SECONDS

logger = get_logger(__name__)

# Type variables for decorator type hints
P = ParamSpec("P")
T = TypeVar("T")


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open."""
    pass


class CircuitBreaker:
    """
    Circuit breaker implementation for external service calls.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Too many failures, requests fail fast
    - HALF_OPEN: Testing if service recovered

    Configuration:
    - failure_threshold: Number of failures before opening (default: 5)
    - timeout_seconds: How long to wait before retrying (default: 60)
    - success_threshold: Successes needed to close from half-open (default: 2)
    """

    def __init__(
        self,
        service_name: str,
        failure_threshold: int = DEFAULT_CIRCUIT_BREAKER_FAILURE_THRESHOLD,
        timeout_seconds: int = DEFAULT_CIRCUIT_BREAKER_TIMEOUT_SECONDS,
        success_threshold: int = DEFAULT_CIRCUIT_BREAKER_SUCCESS_THRESHOLD
    ):
        """
        Initialize circuit breaker.

        Args:
            service_name: Name of the service (e.g., "openai", "azure_devops")
            failure_threshold: Failures before opening circuit
            timeout_seconds: Cooldown period before retry
            success_threshold: Successes needed to close circuit
        """
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.success_threshold = success_threshold

        self.state = CircuitBreakerState(
            service_name=service_name,
            state="CLOSED",
            last_state_change=datetime.now(timezone.utc)
        )

        self._lock = asyncio.Lock()

        logger.info(
            "circuit_breaker_initialized",
            service_name=service_name,
            failure_threshold=failure_threshold,
            timeout_seconds=timeout_seconds
        )

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.

        Args:
            func: Async function to call
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Function result

        Raises:
            CircuitBreakerError: If circuit is open or lock timeout
            Exception: Original exception from function
        """
        # Check state and handle transitions under lock
        try:
            async with asyncio.timeout(LOCK_TIMEOUT_SECONDS):
                async with self._lock:
                    # Check if request should be allowed
                    if not self.state.should_allow_request():
                        logger.warning(
                            "circuit_breaker_open",
                            service_name=self.service_name,
                            failure_count=self.state.failure_count,
                            next_retry=self.state.next_retry_time
                        )
                        raise CircuitBreakerError(
                            f"Circuit breaker OPEN for {self.service_name}. "
                            f"Next retry at {self.state.next_retry_time}"
                        )

                    # Handle OPEN -> HALF_OPEN transition under lock
                    if self.state.state == "OPEN" and self.state.next_retry_time:
                        now = datetime.now(timezone.utc)
                        if now >= self.state.next_retry_time:
                            self.state.state = "HALF_OPEN"
                            self.state.last_state_change = now
                            logger.info(
                                "circuit_breaker_half_open",
                                service_name=self.service_name
                            )
        except asyncio.TimeoutError:
            logger.error(
                "circuit_breaker_lock_timeout",
                service_name=self.service_name,
                timeout_seconds=LOCK_TIMEOUT_SECONDS
            )
            raise CircuitBreakerError(
                f"Circuit breaker lock timeout for {self.service_name} after {LOCK_TIMEOUT_SECONDS}s"
            )

        # Execute the function (outside of lock)
        try:
            result = await func(*args, **kwargs)

            # Record success (acquire lock with timeout)
            try:
                async with asyncio.timeout(LOCK_TIMEOUT_SECONDS):
                    async with self._lock:
                        self.state.record_success(success_threshold=self.success_threshold)
                        logger.debug(
                            "circuit_breaker_success",
                            service_name=self.service_name,
                            state=self.state.state,
                            success_count=self.state.success_count
                        )
            except asyncio.TimeoutError:
                logger.warning(
                    "circuit_breaker_success_lock_timeout",
                    service_name=self.service_name
                )

            return result

        except Exception as e:
            # Record failure (acquire lock with timeout)
            try:
                async with asyncio.timeout(LOCK_TIMEOUT_SECONDS):
                    async with self._lock:
                        self.state.record_failure(
                            failure_threshold=self.failure_threshold,
                            timeout_seconds=self.timeout_seconds
                        )
                        logger.warning(
                            "circuit_breaker_failure",
                            service_name=self.service_name,
                            state=self.state.state,
                            failure_count=self.state.failure_count,
                            error=str(e),
                            error_type=type(e).__name__
                        )
            except asyncio.TimeoutError:
                logger.warning(
                    "circuit_breaker_failure_lock_timeout",
                    service_name=self.service_name
                )

            # Re-raise the original exception
            raise

    def get_state_info(self) -> Dict:
        """
        Get current circuit breaker state.

        Returns:
            Dictionary with state information
        """
        return {
            "service_name": self.service_name,
            "state": self.state.state,
            "failure_count": self.state.failure_count,
            "success_count": self.state.success_count,
            "last_failure_time": self.state.last_failure_time.isoformat() if self.state.last_failure_time else None,
            "last_state_change": self.state.last_state_change.isoformat(),
            "next_retry_time": self.state.next_retry_time.isoformat() if self.state.next_retry_time else None,
            "is_accepting_requests": self.state.should_allow_request()
        }

    async def reset(self) -> None:
        """Manually reset circuit breaker to CLOSED state."""
        async with self._lock:
            self.state.state = "CLOSED"
            self.state.failure_count = 0
            self.state.success_count = 0
            self.state.last_state_change = datetime.now(timezone.utc)
            self.state.next_retry_time = None

            logger.info(
                "circuit_breaker_reset",
                service_name=self.service_name
            )


class CircuitBreakerManager:
    """
    Manages circuit breakers for multiple services.

    Singleton pattern - one instance per service.
    """

    _instances: Dict[str, CircuitBreaker] = {}
    # v2.6.36: Lazy-initialized lock to avoid event loop binding at import time
    _lock: Optional[asyncio.Lock] = None

    @classmethod
    def _get_lock(cls) -> asyncio.Lock:
        """Get or create lock (lazy initialization to avoid event loop issues)."""
        if cls._lock is None:
            cls._lock = asyncio.Lock()
        return cls._lock

    @classmethod
    async def get_breaker(
        cls,
        service_name: str,
        failure_threshold: int = DEFAULT_CIRCUIT_BREAKER_FAILURE_THRESHOLD,
        timeout_seconds: int = DEFAULT_CIRCUIT_BREAKER_TIMEOUT_SECONDS,
        success_threshold: int = DEFAULT_CIRCUIT_BREAKER_SUCCESS_THRESHOLD
    ) -> CircuitBreaker:
        """
        Get or create circuit breaker for service.

        Args:
            service_name: Service identifier
            failure_threshold: Failures before opening
            timeout_seconds: Cooldown period
            success_threshold: Successes to close

        Returns:
            CircuitBreaker instance
        """
        async with cls._get_lock():
            if service_name not in cls._instances:
                cls._instances[service_name] = CircuitBreaker(
                    service_name=service_name,
                    failure_threshold=failure_threshold,
                    timeout_seconds=timeout_seconds,
                    success_threshold=success_threshold
                )
                logger.info(
                    "circuit_breaker_created",
                    service_name=service_name
                )

            return cls._instances[service_name]

    @classmethod
    async def get_all_states(cls) -> Dict[str, Dict]:
        """
        Get state of all circuit breakers.

        Returns:
            Dictionary mapping service name to state info
        """
        states = {}
        for service_name, breaker in cls._instances.items():
            states[service_name] = breaker.get_state_info()

        return states

    @classmethod
    async def reset_all(cls) -> None:
        """Reset all circuit breakers."""
        for breaker in cls._instances.values():
            await breaker.reset()

        logger.info("all_circuit_breakers_reset")


def with_circuit_breaker(
    service_name: str,
    failure_threshold: int = DEFAULT_CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    timeout_seconds: int = DEFAULT_CIRCUIT_BREAKER_TIMEOUT_SECONDS
):
    """
    Decorator to add circuit breaker protection to async functions.

    Usage:
        @with_circuit_breaker("openai", failure_threshold=5, timeout_seconds=60)
        async def call_openai_api():
            # ... API call ...
            pass

    Args:
        service_name: Service identifier
        failure_threshold: Failures before opening
        timeout_seconds: Cooldown period

    Returns:
        Decorated function
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            breaker = await CircuitBreakerManager.get_breaker(
                service_name=service_name,
                failure_threshold=failure_threshold,
                timeout_seconds=timeout_seconds
            )

            return await breaker.call(func, *args, **kwargs)

        return wrapper  # type: ignore[return-value]
    return decorator
