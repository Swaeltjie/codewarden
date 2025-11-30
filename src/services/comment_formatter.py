# src/services/comment_formatter.py
"""
Comment Formatter for Azure DevOps

Formats review results as markdown comments for Azure DevOps PRs.

Version: 1.0.0
"""
from src.models.review_result import ReviewResult, ReviewIssue, IssueSeverity
from typing import List


class CommentFormatter:
    """Formats review results as markdown for Azure DevOps."""
    
    def __init__(self):
        # Emoji/icon mapping for severity levels
        self.severity_icons = {
            IssueSeverity.CRITICAL: "🔴",
            IssueSeverity.HIGH: "🟠",
            IssueSeverity.MEDIUM: "🟡",
            IssueSeverity.LOW: "🔵",
            IssueSeverity.INFO: "ℹ️"
        }
        
        self.recommendation_icons = {
            "approve": "✅",
            "request_changes": "❌",
            "comment": "💬"
        }
    
    def format_summary(self, review_result: ReviewResult) -> str:
        """
        Format complete review result as summary comment.
        
        Creates a comprehensive markdown comment with:
        - Overall recommendation
        - Issue statistics
        - List of issues by severity
        - Review metadata
        
        Args:
            review_result: ReviewResult object
            
        Returns:
            Markdown formatted summary
        """
        lines = []
        
        # Header
        recommendation_icon = self.recommendation_icons.get(
            review_result.recommendation,
            "📝"
        )
        
        lines.append(f"# {recommendation_icon} AI Code Review Results")
        lines.append("")
        
        # Overall recommendation
        recommendation_text = review_result.recommendation.upper().replace("_", " ")
        lines.append(f"**Recommendation:** {recommendation_text}")
        lines.append("")
        
        # Summary if present
        if review_result.summary:
            lines.append(f"**Summary:** {review_result.summary}")
            lines.append("")
        
        # Issue statistics
        issue_counts = self._get_issue_counts(review_result.issues)
        
        if review_result.issues:
            lines.append("## 📊 Issue Summary")
            lines.append("")
            lines.append(f"- 🔴 Critical: {issue_counts['critical']}")
            lines.append(f"- 🟠 High: {issue_counts['high']}")
            lines.append(f"- 🟡 Medium: {issue_counts['medium']}")
            lines.append(f"- 🔵 Low: {issue_counts['low']}")
            lines.append(f"- ℹ️ Info: {issue_counts['info']}")
            lines.append("")
            
            # Critical and High issues (detailed)
            critical_and_high = review_result.get_critical_and_high_issues()
            if critical_and_high:
                lines.append("## 🚨 Critical & High Priority Issues")
                lines.append("")
                for issue in critical_and_high:
                    lines.append(self._format_issue_brief(issue))
                lines.append("")
            
            # Medium and Low issues (brief)
            medium_low_info = [
                i for i in review_result.issues
                if i.severity in [IssueSeverity.MEDIUM, IssueSeverity.LOW, IssueSeverity.INFO]
            ]
            
            if medium_low_info:
                lines.append("<details>")
                lines.append("<summary>📋 Medium, Low & Info Issues (click to expand)</summary>")
                lines.append("")
                for issue in medium_low_info:
                    lines.append(self._format_issue_brief(issue))
                lines.append("</details>")
                lines.append("")
        else:
            lines.append("## ✅ No Issues Found")
            lines.append("")
            lines.append("Great work! No IaC issues detected in this PR.")
            lines.append("")
        
        # Footer with metadata
        lines.append("---")
        lines.append("")
        lines.append("**Review Details:**")
        lines.append(f"- Tokens Used: {review_result.tokens_used:,}")
        lines.append(f"- Estimated Cost: ${review_result.estimated_cost:.4f}")
        lines.append(f"- Review Duration: {review_result.duration_seconds:.1f}s")
        lines.append(f"- Review ID: `{review_result.review_id}`")
        lines.append("")
        lines.append("*🤖 Powered by AI PR Reviewer*")
        
        return "\n".join(lines)
    
    def format_inline_issue(self, issue: ReviewIssue) -> str:
        """
        Format a single issue as inline comment.
        
        Creates a focused comment for a specific line in a file.
        
        Args:
            issue: ReviewIssue object
            
        Returns:
            Markdown formatted inline comment
        """
        icon = self.severity_icons.get(issue.severity, "📝")
        severity_text = issue.severity.upper()
        
        lines = [
            f"{icon} **{severity_text}**: {issue.issue_type}",
            "",
            issue.message,
        ]
        
        if issue.suggestion:
            lines.append("")
            lines.append("**💡 Suggestion:**")
            lines.append(issue.suggestion)
        
        if issue.code_snippet:
            lines.append("")
            lines.append("**Code:**")
            lines.append("```")
            lines.append(issue.code_snippet)
            lines.append("```")
        
        return "\n".join(lines)
    
    def _format_issue_brief(self, issue: ReviewIssue) -> str:
        """
        Format issue as brief one-liner for summary.
        
        Args:
            issue: ReviewIssue object
            
        Returns:
            Brief formatted string
        """
        icon = self.severity_icons.get(issue.severity, "📝")
        
        # Format line number
        line_info = f"L{issue.line_number}" if issue.line_number > 0 else "File-level"
        
        # Build brief description
        brief = f"- {icon} **{issue.issue_type}** ({issue.file_path}:{line_info})"
        brief += f"\n  - {issue.message}"
        
        if issue.suggestion:
            brief += f"\n  - 💡 {issue.suggestion}"
        
        return brief
    
    def _get_issue_counts(self, issues: List[ReviewIssue]) -> dict:
        """Get count of issues by severity."""
        counts = {
            'critical': 0,
            'high': 0,
            'medium': 0,
            'low': 0,
            'info': 0
        }
        
        for issue in issues:
            severity_key = issue.severity.lower()
            if severity_key in counts:
                counts[severity_key] += 1
        
        return counts
