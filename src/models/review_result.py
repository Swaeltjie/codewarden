# src/models/review_result.py
"""
Pydantic Models for Review Results

Data models for AI review results, issues, and recommendations.

Version: 1.0.0
"""
from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum
import uuid
from datetime import datetime, timezone


class IssueSeverity(str, Enum):
    """Severity levels for code review issues."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ReviewIssue(BaseModel):
    """
    Represents a single issue found during code review.
    """
    
    severity: IssueSeverity = Field(..., description="Issue severity level")
    file_path: str = Field(..., description="Path to file with issue")
    line_number: int = Field(ge=0, description="Line number (0 if file-level)")
    issue_type: str = Field(..., description="Type of issue (e.g., PublicEndpoint, HardcodedSecret)")
    message: str = Field(..., description="Human-readable issue description")
    suggestion: Optional[str] = Field(None, description="Suggested fix or remediation")
    code_snippet: Optional[str] = Field(None, description="Relevant code snippet")
    
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
        description="Unique review ID"
    )
    pr_id: int = Field(..., description="Pull request ID")
    issues: List[ReviewIssue] = Field(
        default_factory=list,
        description="List of issues found"
    )
    recommendation: ReviewRecommendation = Field(
        ...,
        description="Overall recommendation"
    )
    summary: Optional[str] = Field(
        None,
        description="Human-readable summary of review"
    )
    duration_seconds: float = Field(
        default=0.0,
        ge=0,
        description="Time taken for review in seconds"
    )
    tokens_used: int = Field(
        default=0,
        ge=0,
        description="Total tokens used by AI"
    )
    estimated_cost: float = Field(
        default=0.0,
        ge=0,
        description="Estimated cost in USD"
    )
    reviewed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of review"
    )
    
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
        # Parse issues
        issues = []
        for issue_data in ai_json.get('issues', []):
            # Use provided file_path as default if not in issue
            if 'file_path' not in issue_data and file_path:
                issue_data['file_path'] = file_path
            
            # Ensure line_number exists
            if 'line_number' not in issue_data:
                issue_data['line_number'] = 0
            
            try:
                issues.append(ReviewIssue(**issue_data))
            except Exception as e:
                # Log but don't fail - skip invalid issues
                import structlog
                logger = structlog.get_logger(__name__)
                logger.warning(
                    "invalid_issue_format",
                    issue_data=issue_data,
                    error=str(e)
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
        
        Args:
            results: List of ReviewResult objects to aggregate
            pr_id: Pull request ID
            
        Returns:
            Aggregated ReviewResult
        """
        if not results:
            return cls.create_empty(pr_id, "No results to aggregate")
        
        # Collect all issues
        all_issues = []
        total_tokens = 0
        total_cost = 0.0
        
        for result in results:
            all_issues.extend(result.issues)
            total_tokens += result.tokens_used
            total_cost += result.estimated_cost
        
        # Determine overall recommendation
        # Priority: critical issues -> high issues -> any issues -> approve
        has_critical = any(r.has_critical_issues() for r in results)
        has_high = any(r.has_high_issues() for r in results)
        
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
