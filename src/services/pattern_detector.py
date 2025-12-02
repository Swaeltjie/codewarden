# src/services/pattern_detector.py
"""
Pattern Detector

Analyzes historical review data to detect recurring issues and patterns.

Version: 2.5.13 - Additional inline comments
"""
import json
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from src.utils.table_storage import (
    get_table_client,
    ensure_table_exists,
    sanitize_odata_value,
    query_entities_paginated
)
from src.utils.config import get_settings
from src.utils.constants import (
    PATTERN_ANALYSIS_DAYS,
    PATTERN_RECURRENCE_THRESHOLD,
    HEALTH_SCORE_MAX,
    HEALTH_SCORE_EXCELLENT,
    HEALTH_SCORE_HEALTHY,
    HEALTH_SCORE_MODERATE,
    HEALTH_SCORE_NEEDS_ATTENTION,
    HEALTH_SCORE_RECURRING_PENALTY,
    REVIEW_HISTORY_TABLE_NAME,
    TABLE_STORAGE_BATCH_SIZE,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PatternDetectorMetrics:
    """
    Metrics for pattern detection operations (v2.5.0).

    Enables observability for:
    - Analysis duration
    - Repository coverage
    - Pattern detection rates
    """
    analysis_started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    analysis_completed_at: Optional[datetime] = None
    repositories_analyzed: int = 0
    reviews_processed: int = 0
    patterns_found: int = 0
    errors_count: int = 0

    @property
    def duration_seconds(self) -> float:
        """Calculate analysis duration."""
        if self.analysis_completed_at:
            return (self.analysis_completed_at - self.analysis_started_at).total_seconds()
        return 0.0

    def to_dict(self) -> Dict:
        """Convert to dictionary for logging/metrics."""
        return {
            "analysis_started_at": self.analysis_started_at.isoformat(),
            "analysis_completed_at": self.analysis_completed_at.isoformat() if self.analysis_completed_at else None,
            "duration_seconds": self.duration_seconds,
            "repositories_analyzed": self.repositories_analyzed,
            "reviews_processed": self.reviews_processed,
            "patterns_found": self.patterns_found,
            "errors_count": self.errors_count
        }


class PatternDetector:
    """
    Detects patterns in historical review data.

    Features:
    - Identifies recurring issues across PRs
    - Detects problematic files (frequent issues)
    - Finds architectural anti-patterns
    - Generates monthly pattern reports
    - Metrics/observability support (v2.5.0)
    """

    def __init__(self) -> None:
        """Initialize pattern detector."""
        self.settings = get_settings()
        self._closed: bool = False
        self._last_metrics: Optional[PatternDetectorMetrics] = None
        logger.info("pattern_detector_initialized")

    @property
    def last_metrics(self) -> Optional[PatternDetectorMetrics]:
        """Get metrics from last analysis run."""
        return self._last_metrics

    async def close(self) -> None:
        """Close resources."""
        self._closed = True
        logger.debug("pattern_detector_closed")

    async def __aenter__(self) -> "PatternDetector":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Async context manager exit - cleanup resources."""
        await self.close()
        return False

    async def analyze_all_repositories(self, days: int = PATTERN_ANALYSIS_DAYS) -> List[Dict]:
        """
        Analyze patterns across all repositories.

        Returns patterns like:
        - Most common issue types
        - Files with recurring issues
        - Team-wide anti-patterns
        - Trend analysis

        Includes metrics collection (v2.5.0).

        Args:
            days: Number of days of history to analyze

        Returns:
            List of pattern dictionaries, one per repository
        """
        # Initialize metrics for this run
        metrics = PatternDetectorMetrics()

        logger.info("pattern_analysis_started", days=days)

        ensure_table_exists('reviewhistory')
        history_table = get_table_client('reviewhistory')

        cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)

        try:
            # Query all reviews from last N days
            query_filter = f"reviewed_at ge datetime'{cutoff_time.isoformat()}'"

            # Use pagination to avoid loading all reviews into memory
            # Apply safety limit DURING iteration to prevent OOM
            reviews = []
            MAX_REVIEWS = 10000
            for review in query_entities_paginated(history_table, query_filter=query_filter, page_size=TABLE_STORAGE_BATCH_SIZE):
                # Check limit BEFORE appending to prevent loading excess data
                if len(reviews) >= MAX_REVIEWS:
                    logger.warning(
                        "pattern_analysis_truncated",
                        max_reviews=MAX_REVIEWS,
                        days=days,
                        reason="Safety limit to prevent memory exhaustion"
                    )
                    break
                reviews.append(review)

            metrics.reviews_processed = len(reviews)

            logger.info(
                "reviews_loaded",
                count=len(reviews),
                days=days
            )

            if not reviews:
                logger.info("no_reviews_found_for_pattern_analysis")
                metrics.analysis_completed_at = datetime.now(timezone.utc)
                self._last_metrics = metrics
                return []

            # Group reviews by repository
            by_repository = defaultdict(list)
            for review in reviews:
                repo = review.get('repository', 'unknown')
                by_repository[repo].append(review)

            # Analyze patterns for each repository
            all_patterns = []

            for repository, repo_reviews in by_repository.items():
                try:
                    patterns = await self._analyze_repository_patterns(
                        repository,
                        repo_reviews,
                        days
                    )
                    all_patterns.append(patterns)
                    metrics.repositories_analyzed += 1

                except Exception as e:
                    metrics.errors_count += 1
                    logger.warning(
                        "repository_pattern_analysis_failed",
                        repository=repository,
                        error=str(e)
                    )
                    continue

            # Calculate total patterns found
            metrics.patterns_found = sum(len(p.get('recurring_issues', [])) for p in all_patterns)
            metrics.analysis_completed_at = datetime.now(timezone.utc)
            self._last_metrics = metrics

            logger.info(
                "pattern_analysis_completed",
                repositories_analyzed=metrics.repositories_analyzed,
                patterns_found=metrics.patterns_found,
                duration_seconds=metrics.duration_seconds,
                errors_count=metrics.errors_count
            )

            return all_patterns

        except Exception as e:
            metrics.errors_count += 1
            metrics.analysis_completed_at = datetime.now(timezone.utc)
            self._last_metrics = metrics

            logger.exception(
                "pattern_analysis_error",
                days=days,
                error=str(e),
                error_type=type(e).__name__,
                metrics=metrics.to_dict()
            )
            return []

    async def _analyze_repository_patterns(
        self,
        repository: str,
        reviews: List[dict],
        days: int
    ) -> Dict:
        """
        Analyze patterns for a specific repository.

        Args:
            repository: Repository name
            reviews: List of review history entities
            days: Analysis period in days

        Returns:
            Dictionary with pattern analysis
        """
        logger.info(
            "repository_analysis_started",
            repository=repository,
            review_count=len(reviews)
        )

        # Aggregate statistics
        total_prs = len(reviews)
        total_issues = sum(r.get('issue_count', 0) for r in reviews)

        # Count issues by severity
        critical_issues = sum(r.get('critical_count', 0) for r in reviews)
        high_issues = sum(r.get('high_count', 0) for r in reviews)
        medium_issues = sum(r.get('medium_count', 0) for r in reviews)
        low_issues = sum(r.get('low_count', 0) for r in reviews)

        # Analyze issue types
        issue_type_freq, recurring_issue_types = self._analyze_issue_types(reviews)

        # Analyze problematic files
        problematic_files = self._analyze_problematic_files(reviews)

        # Analyze trends
        trend_data = self._analyze_trends(reviews, days)

        # Calculate recommendation distribution
        recommendation_dist = Counter(r.get('recommendation') for r in reviews)

        # Calculate average metrics
        avg_issues_per_pr = total_issues / total_prs if total_prs > 0 else 0
        avg_cost = sum(r.get('estimated_cost', 0) for r in reviews) / total_prs if total_prs > 0 else 0

        pattern_report = {
            "repository": repository,
            "analysis_period_days": days,
            "analysis_date": datetime.now(timezone.utc).isoformat(),

            # Summary statistics
            "total_prs_reviewed": total_prs,
            "total_issues_found": total_issues,
            "avg_issues_per_pr": round(avg_issues_per_pr, 2),

            # Severity distribution
            "severity_distribution": {
                "critical": critical_issues,
                "high": high_issues,
                "medium": medium_issues,
                "low": low_issues
            },

            # Recommendation distribution
            "recommendation_distribution": dict(recommendation_dist),

            # Recurring issues (appear in >30% of PRs)
            "recurring_issues": recurring_issue_types,

            # Most common issue types (top 10)
            "top_issue_types": dict(issue_type_freq.most_common(10)),

            # Problematic files (top 10 files with most issues)
            "problematic_files": problematic_files[:10],

            # Trend analysis
            "trends": trend_data,

            # Cost metrics
            "total_cost": round(sum(r.get('estimated_cost', 0) for r in reviews), 2),
            "avg_cost_per_review": round(avg_cost, 4),
            "total_tokens": sum(r.get('tokens_used', 0) for r in reviews)
        }

        logger.info(
            "repository_analysis_completed",
            repository=repository,
            total_issues=total_issues,
            recurring_issues=len(recurring_issue_types),
            problematic_files=len(problematic_files)
        )

        return pattern_report

    def _analyze_issue_types(self, reviews: List[dict]) -> Tuple[Counter, List[Dict]]:
        """
        Analyze issue types across reviews.

        Args:
            reviews: List of review entities

        Returns:
            Tuple of (issue_type_frequency_counter, recurring_issue_type_list)
        """
        issue_type_counter = Counter()
        issue_type_pr_count = defaultdict(set)  # Track which PRs have each issue type

        for review in reviews:
            pr_id = review.get('pr_id')
            issue_types_json = review.get('issue_types', '[]')

            try:
                issue_types = json.loads(issue_types_json)
            except json.JSONDecodeError:
                logger.warning(
                    "invalid_issue_types_json",
                    review_id=review.get('RowKey')
                )
                continue

            for issue_type in issue_types:
                issue_type_counter[issue_type] += 1
                issue_type_pr_count[issue_type].add(pr_id)

        # Identify recurring issues (appear in >threshold% of PRs)
        total_prs = len(reviews)

        recurring_issues = []
        for issue_type, pr_count in issue_type_pr_count.items():
            occurrence_rate = len(pr_count) / total_prs if total_prs > 0 else 0

            if occurrence_rate >= PATTERN_RECURRENCE_THRESHOLD:
                recurring_issues.append({
                    "issue_type": issue_type,
                    "occurrence_count": issue_type_counter[issue_type],
                    "pr_count": len(pr_count),
                    "occurrence_rate": round(occurrence_rate, 3),
                    "severity": "pattern"  # Recurring pattern
                })

        # Sort by occurrence rate
        recurring_issues.sort(key=lambda x: x['occurrence_rate'], reverse=True)

        return issue_type_counter, recurring_issues

    def _analyze_problematic_files(self, reviews: List[dict]) -> List[Dict]:
        """
        Identify files that frequently have issues.

        Args:
            reviews: List of review entities

        Returns:
            List of problematic file dictionaries
        """
        file_issue_count = defaultdict(int)
        file_pr_count = defaultdict(set)
        file_severities = defaultdict(list)

        for review in reviews:
            pr_id = review.get('pr_id')
            files_json = review.get('files_reviewed', '[]')

            try:
                files = json.loads(files_json)
            except json.JSONDecodeError:
                logger.warning(
                    "invalid_files_json",
                    review_id=review.get('RowKey')
                )
                continue

            # For each file, track issues
            issue_count = review.get('issue_count', 0)
            critical = review.get('critical_count', 0)
            high = review.get('high_count', 0)

            # Distribute issues across files (simple approach)
            if files and issue_count > 0:
                for file_path in files:
                    file_issue_count[file_path] += issue_count // len(files)
                    file_pr_count[file_path].add(pr_id)

                    if critical > 0:
                        file_severities[file_path].append('critical')
                    elif high > 0:
                        file_severities[file_path].append('high')

        # Create problematic file list
        problematic_files = []
        for file_path, issue_count in file_issue_count.items():
            if issue_count >= 3:  # At least 3 issues
                problematic_files.append({
                    "file_path": file_path,
                    "total_issues": issue_count,
                    "pr_count": len(file_pr_count[file_path]),
                    "has_critical": 'critical' in file_severities[file_path],
                    "has_high": 'high' in file_severities[file_path]
                })

        # Sort by issue count
        problematic_files.sort(key=lambda x: x['total_issues'], reverse=True)

        return problematic_files

    def _analyze_trends(self, reviews: List[dict], days: int) -> Dict:
        """
        Analyze trends over time.

        Args:
            reviews: List of review entities
            days: Analysis period

        Returns:
            Trend analysis dictionary
        """
        if days < 7:
            # Not enough data for meaningful trends
            return {
                "trend_available": False,
                "message": "Insufficient data for trend analysis (minimum 7 days)"
            }

        # Group reviews by week
        weekly_data = defaultdict(lambda: {
            "pr_count": 0,
            "issue_count": 0,
            "critical_count": 0,
            "high_count": 0
        })

        for review in reviews:
            reviewed_at = review.get('reviewed_at')

            # Parse datetime
            if isinstance(reviewed_at, str):
                try:
                    reviewed_at = datetime.fromisoformat(reviewed_at)
                except ValueError:
                    continue
            elif not isinstance(reviewed_at, datetime):
                continue

            # Get week number
            week_key = reviewed_at.strftime("%Y-W%W")

            weekly_data[week_key]["pr_count"] += 1
            weekly_data[week_key]["issue_count"] += review.get('issue_count', 0)
            weekly_data[week_key]["critical_count"] += review.get('critical_count', 0)
            weekly_data[week_key]["high_count"] += review.get('high_count', 0)

        # Calculate trend direction
        weeks = sorted(weekly_data.keys())
        if len(weeks) >= 2:
            first_week = weekly_data[weeks[0]]
            last_week = weekly_data[weeks[-1]]

            first_avg_issues = first_week["issue_count"] / max(first_week["pr_count"], 1)
            last_avg_issues = last_week["issue_count"] / max(last_week["pr_count"], 1)

            trend_direction = "improving" if last_avg_issues < first_avg_issues else "degrading" if last_avg_issues > first_avg_issues else "stable"
            trend_percentage = ((last_avg_issues - first_avg_issues) / max(first_avg_issues, 0.1)) * 100
        else:
            trend_direction = "unknown"
            trend_percentage = 0.0

        return {
            "trend_available": True,
            "weeks_analyzed": len(weeks),
            "trend_direction": trend_direction,
            "trend_percentage": round(trend_percentage, 1),
            "weekly_summary": {
                week: {
                    "prs": data["pr_count"],
                    "avg_issues_per_pr": round(data["issue_count"] / max(data["pr_count"], 1), 2),
                    "critical_issues": data["critical_count"],
                    "high_issues": data["high_count"]
                }
                for week, data in sorted(weekly_data.items())
            }
        }

    async def get_repository_health_score(self, repository: str, days: int = PATTERN_ANALYSIS_DAYS) -> Dict:
        """
        Calculate health score for a repository.

        Args:
            repository: Repository name
            days: Analysis period

        Returns:
            Health score and metrics
        """
        ensure_table_exists('reviewhistory')
        history_table = get_table_client('reviewhistory')

        cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)

        try:
            # Query reviews for this repository
            safe_repository = sanitize_odata_value(repository)
            query_filter = f"PartitionKey eq '{safe_repository}' and reviewed_at ge datetime'{cutoff_time.isoformat()}'"

            # Use pagination to avoid loading all entities into memory
            reviews = []
            for review in query_entities_paginated(history_table, query_filter=query_filter, page_size=TABLE_STORAGE_BATCH_SIZE):
                reviews.append(review)

            if not reviews:
                return {
                    "repository": repository,
                    "health_score": HEALTH_SCORE_MAX,
                    "status": "unknown",
                    "message": "No reviews found for analysis period"
                }

            # Calculate health metrics
            total_prs = len(reviews)
            total_issues = sum(r.get('issue_count', 0) for r in reviews)
            critical_issues = sum(r.get('critical_count', 0) for r in reviews)
            high_issues = sum(r.get('high_count', 0) for r in reviews)

            avg_issues_per_pr = total_issues / total_prs if total_prs > 0 else 0

            # Calculate health score (0-HEALTH_SCORE_MAX)
            # Start with max, deduct points for issues
            health_score = HEALTH_SCORE_MAX

            # Deduct for average issues per PR (up to 30 points)
            # Thresholds: >10 severe, >5 moderate, >2 minor
            if avg_issues_per_pr > 10:
                health_score -= 30
            elif avg_issues_per_pr > 5:
                health_score -= 20
            elif avg_issues_per_pr > 2:
                health_score -= 10

            # Deduct for critical issues (up to 40 points)
            # Critical issues have highest weight in health score
            if critical_issues > 10:
                health_score -= 40
            elif critical_issues > 5:
                health_score -= 25
            elif critical_issues > 0:
                health_score -= 10

            # Deduct for high issues (up to 20 points)
            # High severity contributes less than critical
            if high_issues > 20:
                health_score -= 20
            elif high_issues > 10:
                health_score -= 10

            # Clamp score to valid range [0, 100]
            health_score = max(0, min(100, health_score))

            # Determine status
            if health_score >= HEALTH_SCORE_HEALTHY:
                status = "healthy"
            elif health_score >= HEALTH_SCORE_MODERATE:
                status = "moderate"
            elif health_score >= HEALTH_SCORE_NEEDS_ATTENTION:
                status = "needs_attention"
            else:
                status = "critical"

            return {
                "repository": repository,
                "health_score": health_score,
                "status": status,
                "metrics": {
                    "total_prs_reviewed": total_prs,
                    "avg_issues_per_pr": round(avg_issues_per_pr, 2),
                    "critical_issues": critical_issues,
                    "high_issues": high_issues,
                    "total_issues": total_issues
                },
                "analysis_period_days": days,
                "analyzed_at": datetime.now(timezone.utc).isoformat()
            }

        except Exception as e:
            logger.exception(
                "health_score_error",
                repository=repository,
                error=str(e)
            )
            return {
                "repository": repository,
                "health_score": 0,
                "status": "error",
                "error": str(e)
            }

    async def get_global_summary(self, days: int = PATTERN_ANALYSIS_DAYS) -> Dict:
        """
        Get global summary across all repositories.

        Args:
            days: Analysis period

        Returns:
            Global summary statistics
        """
        patterns = await self.analyze_all_repositories(days)

        if not patterns:
            return {
                "total_repositories": 0,
                "total_prs": 0,
                "total_issues": 0,
                "message": "No data available for analysis period"
            }

        total_repos = len(patterns)
        total_prs = sum(p.get('total_prs_reviewed', 0) for p in patterns)
        total_issues = sum(p.get('total_issues_found', 0) for p in patterns)
        total_cost = sum(p.get('total_cost', 0) for p in patterns)

        # Find most common issues globally
        all_issue_types = Counter()
        for pattern in patterns:
            issue_types = pattern.get('top_issue_types', {})
            all_issue_types.update(issue_types)

        return {
            "total_repositories": total_repos,
            "total_prs": total_prs,
            "total_issues": total_issues,
            "avg_issues_per_pr": round(total_issues / total_prs, 2) if total_prs > 0 else 0,
            "total_cost": round(total_cost, 2),
            "avg_cost_per_pr": round(total_cost / total_prs, 4) if total_prs > 0 else 0,
            "top_global_issues": dict(all_issue_types.most_common(15)),
            "analysis_period_days": days,
            "analyzed_at": datetime.now(timezone.utc).isoformat()
        }
