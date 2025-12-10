# src/services/comment_formatter.py
"""
Comment Formatter for Azure DevOps

Formats review results as markdown comments for Azure DevOps PRs.

Version: 2.7.2 - Fixed markdown injection vulnerability and type annotations
"""
from src.models.review_result import ReviewResult, ReviewIssue, IssueSeverity
from typing import Dict, List

from src.utils.logging import get_logger

logger = get_logger(__name__)


class CommentFormatter:
    """Formats review results as markdown for Azure DevOps."""

    DEFAULT_ICON = "📝"

    def __init__(self) -> None:
        # Emoji/icon mapping for severity levels
        self.severity_icons: Dict[IssueSeverity, str] = {
            IssueSeverity.CRITICAL: "🔴",
            IssueSeverity.HIGH: "🟠",
            IssueSeverity.MEDIUM: "🟡",
            IssueSeverity.LOW: "🔵",
            IssueSeverity.INFO: "ℹ️",
        }

        self.recommendation_icons: Dict[str, str] = {
            "approve": "✅",
            "request_changes": "❌",
            "comment": "💬",
        }

    def _escape_markdown(self, text: str) -> str:
        """
        Escape markdown special characters to prevent injection.

        Args:
            text: Raw text that may contain markdown special characters

        Returns:
            Text with markdown special characters escaped
        """
        if not text:
            return ""
        # Escape markdown special characters that could be used for injection
        special_chars = [
            "\\",
            "`",
            "*",
            "_",
            "{",
            "}",
            "[",
            "]",
            "(",
            ")",
            "#",
            "+",
            "-",
            ".",
            "!",
            "|",
            "<",
            ">",
        ]
        for char in special_chars:
            text = text.replace(char, "\\" + char)
        return text

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
            review_result.recommendation, self.DEFAULT_ICON
        )

        lines.append(f"# {recommendation_icon} AI Code Review Results")
        lines.append("")

        # Overall recommendation
        recommendation_text = review_result.recommendation.upper().replace("_", " ")
        lines.append(f"**Recommendation:** {recommendation_text}")
        lines.append("")

        # Summary if present (escape to prevent markdown injection)
        if review_result.summary and review_result.summary.strip():
            lines.append(f"**Summary:** {self._escape_markdown(review_result.summary)}")
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
                i
                for i in review_result.issues
                if i.severity
                in [IssueSeverity.MEDIUM, IssueSeverity.LOW, IssueSeverity.INFO]
            ]

            if medium_low_info:
                lines.append("<details>")
                lines.append(
                    "<summary>📋 Medium, Low & Info Issues (click to expand)</summary>"
                )
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
        icon = self.severity_icons.get(issue.severity, self.DEFAULT_ICON)
        # Defensive enum handling
        severity_text = (
            issue.severity.value
            if hasattr(issue.severity, "value")
            else str(issue.severity)
        ).upper()

        lines = [
            f"{icon} **{severity_text}**: {self._escape_markdown(issue.issue_type)}",
            "",
            self._escape_markdown(issue.message),
        ]

        if issue.suggestion and issue.suggestion.strip():
            lines.append("")
            lines.append("**💡 Suggestion:**")
            lines.append(self._escape_markdown(issue.suggestion))

        if issue.code_snippet and issue.code_snippet.strip():
            lines.append("")
            lines.append("**Code:**")
            # Escape triple backticks to prevent breaking out of code block
            safe_snippet = issue.code_snippet.replace("```", "\\`\\`\\`")
            lines.append("```")
            lines.append(safe_snippet)
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
        icon = self.severity_icons.get(issue.severity, self.DEFAULT_ICON)

        # Format line number
        line_info = f"L{issue.line_number}" if issue.line_number > 0 else "File-level"

        # Build brief description (escape user-controlled content)
        brief = f"- {icon} **{self._escape_markdown(issue.issue_type)}** ({self._escape_markdown(issue.file_path)}:{line_info})"
        brief += f"\n  - {self._escape_markdown(issue.message)}"

        if issue.suggestion and issue.suggestion.strip():
            brief += f"\n  - 💡 {self._escape_markdown(issue.suggestion)}"

        return brief

    def _get_issue_counts(self, issues: List[ReviewIssue]) -> Dict[str, int]:
        """Get count of issues by severity."""
        counts: Dict[str, int] = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "info": 0,
        }

        for issue in issues:
            # Defensive enum handling
            severity_key = (
                issue.severity.value
                if hasattr(issue.severity, "value")
                else str(issue.severity)
            ).lower()
            if severity_key in counts:
                counts[severity_key] += 1
            else:
                # Log unexpected severity level for debugging
                logger.warning(
                    "unexpected_severity_level",
                    severity=severity_key,
                    issue_type=issue.issue_type,
                )

        return counts
