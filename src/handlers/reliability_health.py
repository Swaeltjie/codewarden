# src/handlers/reliability_health.py
"""
Reliability Health Check Handler

Provides health and metrics endpoints for monitoring reliability features:
- Circuit breaker states
- Response cache statistics
- Idempotency statistics

Version: 2.7.3 - Fixed health score logic, sanitized errors, added bool check for days
"""
import re
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from src.services.circuit_breaker import CircuitBreakerManager
from src.services.response_cache import ResponseCache
from src.services.idempotency_checker import IdempotencyChecker
from src.utils.constants import (
    HEALTH_SCORE_MAX,
    HEALTH_SCORE_EXCELLENT,
    HEALTH_SCORE_HEALTHY,
    HEALTH_SCORE_MODERATE,
    HEALTH_SCORE_DEGRADED,
    HEALTH_CHECK_CACHE_EFFICIENCY_LOW,
    HEALTH_CHECK_CACHE_EFFICIENCY_MODERATE,
    HEALTH_CHECK_DUPLICATE_RATE_HIGH,
    HEALTH_CHECK_DUPLICATE_RATE_MODERATE,
)
from src.utils.logging import get_logger
from src.utils.config import __version__

logger = get_logger(__name__)


class ReliabilityHealthHandler:
    """
    Handler for reliability health check endpoints.

    Provides insights into:
    - Circuit breaker states (open/closed/half-open)
    - Cache hit rates and cost savings
    - Idempotency duplicate detection rates
    """

    def __init__(self) -> None:
        """Initialize reliability health handler."""
        self.response_cache = ResponseCache()
        self.idempotency_checker = IdempotencyChecker()
        logger.info("reliability_health_handler_initialized")

    async def get_health_status(self) -> Dict[str, Any]:
        """
        Get comprehensive health status for all reliability features.

        Returns:
            Dictionary with health status and metrics
        """
        logger.info("reliability_health_check_requested")

        try:
            # Get circuit breaker states
            circuit_breaker_states = await CircuitBreakerManager.get_all_states()

            # Get cache statistics (last 30 days)
            cache_stats = await self.response_cache.get_cache_statistics()

            # Get idempotency statistics (last 7 days)
            idempotency_stats = await self.idempotency_checker.get_statistics(days=7)

            # Determine overall health
            overall_health = self._calculate_overall_health(
                circuit_breaker_states, cache_stats, idempotency_stats
            )

            response = {
                "status": overall_health["status"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "version": __version__,
                "features": {
                    "circuit_breakers": {
                        "status": overall_health["circuit_breaker_status"],
                        "services": circuit_breaker_states,
                        "summary": self._summarize_circuit_breakers(
                            circuit_breaker_states
                        ),
                    },
                    "response_cache": {
                        "status": overall_health["cache_status"],
                        "statistics": cache_stats,
                        "health": self._assess_cache_health(cache_stats),
                    },
                    "idempotency": {
                        "status": overall_health["idempotency_status"],
                        "statistics": idempotency_stats,
                        "health": self._assess_idempotency_health(idempotency_stats),
                    },
                },
                "overall_health_score": overall_health["health_score"],
            }

            logger.info(
                "reliability_health_check_completed",
                overall_status=overall_health["status"],
                health_score=overall_health["health_score"],
            )

            return response

        except Exception as e:
            logger.exception(
                "reliability_health_check_failed",
                error=str(e),
                error_type=type(e).__name__,
            )

            # Return sanitized error - don't expose internal details
            return {
                "status": "error",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": "Failed to retrieve health status",
                "error_code": "HEALTH_CHECK_ERROR",
            }

    def _calculate_overall_health(
        self, circuit_breaker_states: Dict, cache_stats: Dict, idempotency_stats: Dict
    ) -> Dict[str, Any]:
        """
        Calculate overall health status.

        Args:
            circuit_breaker_states: Circuit breaker status for all services
            cache_stats: Cache statistics
            idempotency_stats: Idempotency statistics

        Returns:
            Overall health assessment
        """
        health_score = HEALTH_SCORE_MAX

        # Circuit breaker health
        cb_open_count = sum(
            1
            for state in circuit_breaker_states.values()
            if state.get("state") == "OPEN"
        )
        cb_half_open_count = sum(
            1
            for state in circuit_breaker_states.values()
            if state.get("state") == "HALF_OPEN"
        )

        if cb_open_count > 0:
            health_score -= 40  # Critical: services unavailable
            cb_status = "degraded"
        elif cb_half_open_count > 0:
            health_score -= 20  # Warning: services recovering
            cb_status = "recovering"
        else:
            cb_status = "healthy"

        # Cache health
        cache_efficiency = cache_stats.get("cache_efficiency_percent", 0)
        if cache_efficiency < HEALTH_CHECK_CACHE_EFFICIENCY_LOW:
            health_score -= 10  # Low cache efficiency
            cache_status = "low_efficiency"
        elif cache_efficiency < HEALTH_CHECK_CACHE_EFFICIENCY_MODERATE:
            cache_status = "moderate_efficiency"
        else:
            cache_status = "high_efficiency"

        # Idempotency health
        duplicate_rate = idempotency_stats.get("duplicate_rate_percent", 0)
        if duplicate_rate > HEALTH_CHECK_DUPLICATE_RATE_HIGH:
            health_score -= 15  # High duplicate rate indicates issues
            idempotency_status = "high_duplicates"
        elif duplicate_rate > HEALTH_CHECK_DUPLICATE_RATE_MODERATE:
            idempotency_status = "moderate_duplicates"
        else:
            idempotency_status = "healthy"

        # Determine overall status
        if health_score >= HEALTH_SCORE_EXCELLENT:
            overall_status = "excellent"
        elif health_score >= HEALTH_SCORE_HEALTHY:
            overall_status = "healthy"
        elif health_score >= HEALTH_SCORE_DEGRADED:
            overall_status = "degraded"
        else:
            overall_status = "unhealthy"

        return {
            "status": overall_status,
            "health_score": health_score,
            "circuit_breaker_status": cb_status,
            "cache_status": cache_status,
            "idempotency_status": idempotency_status,
        }

    def _summarize_circuit_breakers(self, states: Dict) -> Dict[str, int]:
        """
        Summarize circuit breaker states.

        Args:
            states: Circuit breaker states for all services

        Returns:
            Count of services in each state
        """
        summary = {
            "total_services": len(states),
            "closed": 0,
            "open": 0,
            "half_open": 0,
        }

        for state in states.values():
            current_state = state.get("state", "unknown").lower()
            if current_state == "closed":
                summary["closed"] += 1
            elif current_state == "open":
                summary["open"] += 1
            elif current_state == "half_open":
                summary["half_open"] += 1

        return summary

    def _assess_cache_health(self, cache_stats: Dict) -> str:
        """
        Assess cache health based on statistics.

        Args:
            cache_stats: Cache statistics

        Returns:
            Health assessment string
        """
        cache_efficiency = cache_stats.get("cache_efficiency_percent", 0)
        active_entries = cache_stats.get("active_entries", 0)
        expired_entries = cache_stats.get("expired_entries", 0)

        issues = []

        if cache_efficiency < HEALTH_CHECK_CACHE_EFFICIENCY_LOW:
            issues.append(
                f"Low cache efficiency (<{HEALTH_CHECK_CACHE_EFFICIENCY_LOW}%)"
            )

        if active_entries == 0:
            issues.append("No cached entries")

        if active_entries > 0 and expired_entries > active_entries * 0.5:
            issues.append(f"High expired ratio ({expired_entries}/{active_entries})")

        if issues:
            return "Issues: " + ", ".join(issues)
        elif cache_efficiency > HEALTH_CHECK_CACHE_EFFICIENCY_MODERATE:
            return "Excellent cache performance"
        elif cache_efficiency > HEALTH_CHECK_CACHE_EFFICIENCY_LOW:
            return "Good cache performance"
        else:
            return "Building cache"

    def _assess_idempotency_health(self, idempotency_stats: Dict) -> str:
        """
        Assess idempotency health based on statistics.

        Args:
            idempotency_stats: Idempotency statistics

        Returns:
            Health assessment string
        """
        duplicate_rate = idempotency_stats.get("duplicate_rate_percent", 0)
        total_requests = idempotency_stats.get("total_requests", 0)

        if total_requests == 0:
            return "No requests tracked yet"

        if duplicate_rate > 20:
            return f"High duplicate rate ({duplicate_rate:.1f}%) - investigate webhook retries"
        elif duplicate_rate > 10:
            return f"Moderate duplicate rate ({duplicate_rate:.1f}%) - normal retry behavior"
        elif duplicate_rate > 0:
            return f"Low duplicate rate ({duplicate_rate:.1f}%) - healthy"
        else:
            return "No duplicates detected - excellent"

    async def get_circuit_breaker_status(self) -> Dict[str, Any]:
        """
        Get detailed circuit breaker status.

        Returns:
            Circuit breaker states for all services
        """
        try:
            states = await CircuitBreakerManager.get_all_states()

            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "circuit_breakers": states,
                "summary": self._summarize_circuit_breakers(states),
            }

        except Exception as e:
            logger.exception("circuit_breaker_status_failed", error=str(e))
            return {
                "status": "error",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": "Failed to retrieve circuit breaker status",
                "error_code": "CIRCUIT_BREAKER_ERROR",
            }

    async def get_cache_statistics(
        self, repository: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get detailed cache statistics.

        Args:
            repository: Optional repository filter

        Returns:
            Cache statistics
        """
        # Validate repository parameter
        if repository is not None:
            if not isinstance(repository, str):
                logger.warning(
                    "invalid_repository_type", repository_type=type(repository).__name__
                )
                return {
                    "status": "error",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "error": "repository parameter must be a string",
                    "error_type": "ValueError",
                }
            if not re.match(r"^[a-zA-Z0-9_\-\.]{1,500}$", repository):
                logger.warning("invalid_repository_parameter", repository=repository)
                return {
                    "status": "error",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "error": "Invalid repository name format (allowed: alphanumeric, dash, underscore, dot, max 500 chars)",
                    "error_type": "ValueError",
                }

        try:
            stats = await self.response_cache.get_cache_statistics(
                repository=repository
            )

            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "cache_statistics": stats,
                "health_assessment": self._assess_cache_health(stats),
            }

        except Exception as e:
            logger.exception("cache_statistics_failed", error=str(e))
            return {
                "status": "error",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": "Failed to retrieve cache statistics",
                "error_code": "CACHE_STATS_ERROR",
            }

    async def get_idempotency_statistics(self, days: int = 7) -> Dict[str, Any]:
        """
        Get detailed idempotency statistics.

        Args:
            days: Number of days to analyze (must be between 1 and 365)

        Returns:
            Idempotency statistics
        """
        # Validate days parameter (check bool first since bool is subclass of int)
        if (
            isinstance(days, bool)
            or not isinstance(days, int)
            or days < 1
            or days > 365
        ):
            logger.warning(
                "invalid_days_parameter", days=days, days_type=type(days).__name__
            )
            return {
                "status": "error",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": "days parameter must be an integer between 1 and 365",
                "error_code": "INVALID_PARAMETER",
            }

        try:
            stats = await self.idempotency_checker.get_statistics(days=days)

            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "idempotency_statistics": stats,
                "health_assessment": self._assess_idempotency_health(stats),
            }

        except Exception as e:
            logger.exception("idempotency_statistics_failed", error=str(e))
            return {
                "status": "error",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": "Failed to retrieve idempotency statistics",
                "error_code": "IDEMPOTENCY_STATS_ERROR",
            }

    async def reset_circuit_breakers(self) -> Dict[str, Any]:
        """
        Manually reset all circuit breakers (admin operation).

        Returns:
            Reset confirmation
        """
        try:
            logger.warning("circuit_breakers_manual_reset_requested")

            await CircuitBreakerManager.reset_all()

            logger.info("circuit_breakers_reset_completed")

            return {
                "status": "success",
                "message": "All circuit breakers reset to CLOSED state",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.exception("circuit_breaker_reset_failed", error=str(e))
            return {
                "status": "error",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": "Failed to reset circuit breakers",
                "error_code": "CIRCUIT_BREAKER_RESET_ERROR",
            }

    async def cleanup_expired_cache(self) -> Dict[str, Any]:
        """
        Manually trigger cache cleanup (admin operation).

        Returns:
            Cleanup results
        """
        try:
            logger.info("cache_cleanup_requested")

            deleted_count = await self.response_cache.cleanup_expired_entries()

            logger.info("cache_cleanup_completed", deleted_count=deleted_count)

            return {
                "status": "success",
                "deleted_entries": deleted_count,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.exception("cache_cleanup_failed", error=str(e))
            return {
                "status": "error",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": "Failed to cleanup expired cache",
                "error_code": "CACHE_CLEANUP_ERROR",
            }
