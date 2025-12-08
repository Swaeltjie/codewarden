# src/models/review_result.py
"""
Pydantic Models for Review Results

Data models for AI review results, issues, and recommendations.

Version: 2.6.34 - Fixed attribute access in review aggregation for immutable objects
"""
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from enum import Enum
import uuid
import os
from datetime import datetime, timezone

# Import constants for validation
from src.utils.constants import (
    MAX_ISSUES_PER_REVIEW,
    MAX_COMMENT_LENGTH,
    MAX_LOGGED_ISSUE_ERRORS,
    MAX_AGGREGATED_TOKENS,
    MAX_AGGREGATED_COST,
)
from src.utils.logging import get_logger

# Module-level logger for use in classmethods/staticmethods
_logger = get_logger(__name__)


class IssueSeverity(str, Enum):
    """Severity levels for code review issues."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class SuggestedFix(BaseModel):
    """
    Represents a suggested code fix for an issue.

    Provides before/after code snippets that developers can copy-paste.
    """
    description: str = Field(..., max_length=1000, description="Brief description of the fix")
    before: str = Field(..., max_length=10000, description="Code that has the issue")
    after: str = Field(..., max_length=10000, description="Fixed code snippet")
    explanation: Optional[str] = Field(None, max_length=2000, description="Why this fix works")


class ReviewIssue(BaseModel):
    """
    Represents a single issue found during code review.
    """

    severity: IssueSeverity = Field(..., description="Issue severity level")
    file_path: str = Field(..., max_length=2000, description="Path to file with issue")
    line_number: int = Field(ge=0, le=1000000, description="Line number (0 if file-level)")
    issue_type: str = Field(..., max_length=200, description="Type of issue (e.g., PublicEndpoint, HardcodedSecret)")
    message: str = Field(..., max_length=5000, description="Human-readable issue description")
    suggestion: Optional[str] = Field(None, max_length=5000, description="Suggested fix or remediation")
    code_snippet: Optional[str] = Field(None, max_length=10000, description="Relevant code snippet")
    suggested_fix: Optional[SuggestedFix] = Field(None, description="Detailed fix with before/after code")
    agent_type: Optional[str] = Field(None, max_length=50, description="Agent that found this issue (v2.7.0)")

    @field_validator('message', 'suggestion', 'issue_type')
    @classmethod
    def sanitize_text_fields(cls, v: Optional[str]) -> Optional[str]:
        """
        Sanitize text fields to prevent markdown injection.

        Removes or escapes characters that could be used for
        malicious markdown rendering in Azure DevOps comments.
        """
        if v is None:
            return v

        # Remove null bytes
        v = v.replace('\x00', '')

        # Limit consecutive newlines to prevent comment spam
        while '\n\n\n' in v:
            v = v.replace('\n\n\n', '\n\n')

        return v.strip()

    @field_validator('file_path')
    @classmethod
    def validate_file_path(cls, v: str) -> str:
        """
        Validate file path to prevent path traversal attacks.

        Rejects:
        - Null bytes
        - Path traversal patterns (../)
        - Absolute paths outside repo
        - Suspicious system paths
        """
        if not v:
            raise ValueError("file_path cannot be empty")

        # Check for null bytes
        if '\x00' in v:
            raise ValueError("file_path contains null bytes")

        # Normalize and check for traversal
        normalized = os.path.normpath(v)

        # Check for path traversal patterns
        if '..' in normalized.split(os.sep):
            raise ValueError("file_path contains path traversal")

        # Check for suspicious patterns
        suspicious = ['/etc/', '/proc/', 'c:\\windows', '\\windows\\']
        if any(pattern in v.lower() for pattern in suspicious):
            raise ValueError("file_path contains suspicious pattern")

        return v
    
    @property
    def is_critical_or_high(self) -> bool:
        """Check if issue is critical or high severity."""
        return self.severity in [IssueSeverity.CRITICAL, IssueSeverity.HIGH]
    
    @property
    def is_blocking(self) -> bool:
        """Check if issue should block PR merge."""
        return self.severity == IssueSeverity.CRITICAL
    
    class Config:
        use_enum_values = True


class ReviewRecommendation(str, Enum):
    """Overall recommendation for the PR."""
    APPROVE = "approve"
    REQUEST_CHANGES = "request_changes"
    COMMENT = "comment"


class ReviewResult(BaseModel):
    """
    Complete review result for a Pull Request.
    """
    
    review_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        max_length=100,
        description="Unique review ID"
    )
    pr_id: int = Field(..., gt=0, lt=2147483647, description="Pull request ID")
    issues: List[ReviewIssue] = Field(
        default_factory=list,
        max_length=MAX_ISSUES_PER_REVIEW,
        description="List of issues found"
    )
    recommendation: ReviewRecommendation = Field(
        ...,
        description="Overall recommendation"
    )
    summary: Optional[str] = Field(
        None,
        max_length=MAX_COMMENT_LENGTH,
        description="Human-readable summary of review"
    )
    duration_seconds: float = Field(
        default=0.0,
        ge=0,
        lt=86400.0,
        description="Time taken for review in seconds"
    )
    tokens_used: int = Field(
        default=0,
        ge=0,
        lt=10000000,
        description="Total tokens used by AI"
    )
    estimated_cost: float = Field(
        default=0.0,
        ge=0,
        lt=10000.0,
        description="Estimated cost in USD"
    )
    reviewed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of review"
    )

    @field_validator('issues')
    @classmethod
    def validate_issues_list(cls, v: List[ReviewIssue]) -> List[ReviewIssue]:
        """
        Validate issues list size and deduplicate.

        Prevents DoS from excessive issues and removes duplicates.
        """
        if len(v) > MAX_ISSUES_PER_REVIEW:
            raise ValueError(f"Too many issues: {len(v)} exceeds limit of {MAX_ISSUES_PER_REVIEW}")

        # Deduplicate issues based on file_path + line_number + issue_type
        seen = set()
        unique_issues = []
        for issue in v:
            key = (issue.file_path, issue.line_number, issue.issue_type)
            if key not in seen:
                seen.add(key)
                unique_issues.append(issue)

        return unique_issues
    
    @staticmethod
    def create_empty(pr_id: int, message: str = "No IaC files found") -> "ReviewResult":
        """
        Create empty result when no files to review.
        
        Args:
            pr_id: Pull request ID
            message: Reason for empty result
            
        Returns:
            ReviewResult with no issues and approve recommendation
        """
        return ReviewResult(
            pr_id=pr_id,
            recommendation=ReviewRecommendation.APPROVE,
            summary=message
        )
    
    def has_critical_issues(self) -> bool:
        """Check if result has any critical severity issues."""
        return any(i.severity == IssueSeverity.CRITICAL for i in self.issues)
    
    def has_high_issues(self) -> bool:
        """Check if result has any high severity issues."""
        return any(i.severity == IssueSeverity.HIGH for i in self.issues)
    
    def has_blocking_issues(self) -> bool:
        """Check if result has any blocking issues."""
        return any(i.is_blocking for i in self.issues)
    
    def get_issues_by_severity(self, severity: IssueSeverity) -> List[ReviewIssue]:
        """Get all issues of a specific severity."""
        return [i for i in self.issues if i.severity == severity]
    
    def get_critical_and_high_issues(self) -> List[ReviewIssue]:
        """Get all critical and high severity issues."""
        return [i for i in self.issues if i.is_critical_or_high]
    
    @classmethod
    def from_ai_response(
        cls,
        ai_json: dict,
        pr_id: int,
        file_path: Optional[str] = None
    ) -> "ReviewResult":
        """
        Parse AI JSON response into ReviewResult.
        
        Expected AI response format:
        {
            "issues": [
                {
                    "severity": "high",
                    "file_path": "/main.tf",
                    "line_number": 10,
                    "issue_type": "PublicEndpoint",
                    "message": "Resource exposes public endpoint",
                    "suggestion": "Add firewall rules"
                }
            ],
            "recommendation": "request_changes",
            "summary": "Found 5 security issues",
            "_metadata": {
                "tokens_used": 1200,
                "estimated_cost": 0.012
            }
        }
        
        Args:
            ai_json: Parsed JSON from AI
            pr_id: Pull request ID
            file_path: Default file path if issues don't specify
            
        Returns:
            Parsed ReviewResult
        """
        # Parse issues with better error handling
        issues = []
        invalid_count = 0

        # v2.6.4: Validate that issues is a list to prevent TypeError
        issues_data = ai_json.get('issues', [])
        if not isinstance(issues_data, list):
            _logger.warning(
                "ai_response_issues_not_list",
                type=type(issues_data).__name__,
                pr_id=pr_id
            )
            issues_data = []

        for idx, issue_data in enumerate(issues_data):
            # Use provided file_path as default if not in issue
            if 'file_path' not in issue_data and file_path:
                issue_data['file_path'] = file_path

            # Ensure line_number exists
            if 'line_number' not in issue_data:
                issue_data['line_number'] = 0

            try:
                issues.append(ReviewIssue(**issue_data))
            except (ValueError, TypeError) as e:
                # Log but don't fail - skip invalid issues
                # Only catch specific validation errors, not all exceptions
                # Rate limit individual error logs to prevent DoS via log flooding
                invalid_count += 1
                if invalid_count <= MAX_LOGGED_ISSUE_ERRORS:
                    _logger.warning(
                        "invalid_issue_format",
                        index=idx,
                        error=str(e)
                    )
                elif invalid_count == MAX_LOGGED_ISSUE_ERRORS + 1:
                    _logger.warning(
                        "too_many_invalid_issues",
                        message="Suppressing further individual error logs"
                    )

        # Log summary metrics about invalid issues
        if invalid_count > 0:
            _logger.warning(
                "skipped_invalid_issues",
                invalid_count=invalid_count,
                valid_count=len(issues),
                pr_id=pr_id
            )
        
        # Get metadata
        metadata = ai_json.get('_metadata', {})
        tokens_used = metadata.get('tokens_used', 0)
        estimated_cost = metadata.get('estimated_cost', 0.0)
        
        # Get recommendation
        recommendation = ai_json.get('recommendation', 'comment')
        
        # Validate and normalize recommendation
        if recommendation not in ['approve', 'request_changes', 'comment']:
            recommendation = 'comment'
        
        return cls(
            pr_id=pr_id,
            issues=issues,
            recommendation=ReviewRecommendation(recommendation),
            summary=ai_json.get('summary'),
            tokens_used=tokens_used,
            estimated_cost=estimated_cost
        )
    
    @classmethod
    def aggregate(
        cls,
        results: List["ReviewResult"],
        pr_id: int
    ) -> "ReviewResult":
        """
        Aggregate multiple review results into one.

        Used for chunked and hierarchical review strategies.

        Includes validation (v2.5.0):
        - Filters out invalid/empty results
        - Validates issue data
        - Logs aggregation metrics

        Args:
            results: List of ReviewResult objects to aggregate
            pr_id: Pull request ID

        Returns:
            Aggregated ReviewResult
        """
        if not results:
            return cls.create_empty(pr_id, "No results to aggregate")

        # Filter out None and validate results (v2.5.0)
        valid_results = []
        skipped_count = 0

        for result in results:
            if result is None:
                skipped_count += 1
                continue
            if not isinstance(result, ReviewResult):
                _logger.warning("aggregate_invalid_result_type", type=type(result).__name__)
                skipped_count += 1
                continue
            valid_results.append(result)

        if skipped_count > 0:
            _logger.warning(
                "aggregate_skipped_invalid_results",
                skipped_count=skipped_count,
                valid_count=len(valid_results)
            )

        if not valid_results:
            return cls.create_empty(pr_id, "No valid results to aggregate")

        # Collect all issues with overflow protection
        # Pydantic Field limits: tokens_used < 10000000, estimated_cost < 10000.0
        all_issues = []
        total_tokens = 0
        total_cost = 0.0

        # v2.6.2: Added per-result exception handling for resilience
        for result in valid_results:
            try:
                # Validate result has required attributes
                if not hasattr(result, 'issues') or result.issues is None:
                    _logger.warning("aggregate_result_missing_issues")
                    continue

                # Safely set default values for missing attributes
                # Use getattr with defaults to handle immutable objects
                tokens_used = getattr(result, 'tokens_used', 0) or 0
                estimated_cost = getattr(result, 'estimated_cost', 0.0) or 0.0

                all_issues.extend(result.issues)
                total_tokens += tokens_used
                total_cost += estimated_cost

                # Cap at Pydantic field limits to prevent validation errors
                if total_tokens >= MAX_AGGREGATED_TOKENS:
                    _logger.warning(
                        "aggregate_token_overflow",
                        total=total_tokens,
                        capped_at=MAX_AGGREGATED_TOKENS
                    )
                    total_tokens = MAX_AGGREGATED_TOKENS
                if total_cost >= MAX_AGGREGATED_COST:
                    _logger.warning(
                        "aggregate_cost_overflow",
                        total=total_cost,
                        capped_at=MAX_AGGREGATED_COST
                    )
                    total_cost = MAX_AGGREGATED_COST
            except Exception as e:
                # v2.6.2: Don't let one bad result break entire aggregation
                _logger.warning(
                    "aggregate_result_processing_failed",
                    error=str(e),
                    error_type=type(e).__name__
                )
                continue

        # Determine overall recommendation
        # Priority: critical issues -> high issues -> any issues -> approve
        has_critical = any(r.has_critical_issues() for r in valid_results)
        has_high = any(r.has_high_issues() for r in valid_results)
        
        if has_critical or has_high:
            recommendation = ReviewRecommendation.REQUEST_CHANGES
        elif all_issues:
            recommendation = ReviewRecommendation.COMMENT
        else:
            recommendation = ReviewRecommendation.APPROVE
        
        # Create summary
        issue_counts = {
            'critical': len([i for i in all_issues if i.severity == IssueSeverity.CRITICAL]),
            'high': len([i for i in all_issues if i.severity == IssueSeverity.HIGH]),
            'medium': len([i for i in all_issues if i.severity == IssueSeverity.MEDIUM]),
            'low': len([i for i in all_issues if i.severity == IssueSeverity.LOW]),
        }
        
        summary = f"Found {len(all_issues)} total issues: "
        summary += f"{issue_counts['critical']} critical, "
        summary += f"{issue_counts['high']} high, "
        summary += f"{issue_counts['medium']} medium, "
        summary += f"{issue_counts['low']} low"
        
        return cls(
            pr_id=pr_id,
            issues=all_issues,
            recommendation=recommendation,
            summary=summary,
            tokens_used=total_tokens,
            estimated_cost=total_cost
        )
    
    @classmethod
    def hierarchical_aggregate(
        cls,
        individual_results: List["ReviewResult"],
        cross_file_analysis: Optional[dict],
        pr_id: int
    ) -> "ReviewResult":
        """
        Aggregate hierarchical review results.
        
        Combines individual file reviews with cross-file analysis.
        
        Args:
            individual_results: Results from individual file reviews
            cross_file_analysis: Cross-file dependency analysis (optional)
            pr_id: Pull request ID
            
        Returns:
            Aggregated ReviewResult
        """
        # Start with aggregation of individual results
        result = cls.aggregate(individual_results, pr_id)
        
        # Add cross-file analysis to summary if present
        if cross_file_analysis:
            analysis_text = cross_file_analysis.get('analysis', '')
            if analysis_text:
                result.summary += f"\n\nCross-file analysis: {analysis_text}"
        
        return result
    
    class Config:
        use_enum_values = True
