# src/prompts/factory.py
"""
Prompt Factory for AI Code Reviews

Generates specialized prompts for different file types and review strategies.

Version: 2.5.12 - Comprehensive type hints
"""
from typing import List, Dict, Optional
import re
from src.models.pr_event import FileChange, FileType
from src.services.diff_parser import DiffParser
from src.utils.constants import (
    PROMPT_MAX_TITLE_LENGTH,
    PROMPT_MAX_PATH_LENGTH,
    PROMPT_MAX_MESSAGE_LENGTH,
    PROMPT_MAX_ISSUE_TYPE_LENGTH,
    LOG_FIELD_MAX_LENGTH,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


class PromptFactory:
    """
    Generates AI review prompts for different scenarios.

    Creates specialized prompts for:
    - Different file types (Terraform, Ansible, etc.)
    - Different review strategies (single-pass, chunked, hierarchical)
    - Learning context integration
    """

    # Maximum lengths for user-controlled inputs (DoS protection)
    # Use centralized constants
    MAX_TITLE_LENGTH = PROMPT_MAX_TITLE_LENGTH
    MAX_PATH_LENGTH = PROMPT_MAX_PATH_LENGTH
    MAX_MESSAGE_LENGTH = PROMPT_MAX_MESSAGE_LENGTH
    MAX_ISSUE_TYPE_LENGTH = PROMPT_MAX_ISSUE_TYPE_LENGTH

    def __init__(self) -> None:
        self.diff_parser = DiffParser()

    @staticmethod
    def _sanitize_user_input(text: str, max_length: int = 1000) -> str:
        """
        Sanitize user-controlled text to prevent prompt injection.

        This method protects against prompt injection attacks by:
        1. Limiting input length (DoS protection)
        2. Removing potential instruction markers
        3. Escaping special characters that could break prompt structure

        Args:
            text: User-controlled text (PR title, file path, etc.)
            max_length: Maximum allowed length

        Returns:
            Sanitized text safe for prompt inclusion
        """
        if not text:
            return ""

        # Truncate to max length
        text = text[:max_length]

        # Remove common prompt injection patterns
        # - Remove markdown headers that could create new sections
        # - Remove instruction-like patterns
        # - Remove potential delimiter confusion
        dangerous_patterns = [
            r'(?i)ignore\s+(all\s+)?(previous|above|prior)\s+instructions?',
            r'(?i)disregard\s+(all\s+)?(previous|above|prior)',
            r'(?i)new\s+instructions?:',
            r'(?i)system\s*:',
            r'(?i)assistant\s*:',
            r'(?i)user\s*:',
            r'---+',  # Markdown horizontal rules that could break sections
        ]

        for pattern in dangerous_patterns:
            text = re.sub(pattern, '[REDACTED]', text)

        # Replace multiple newlines with single newline to prevent section breaks
        text = re.sub(r'\n{3,}', '\n\n', text)

        # Log if sanitization modified the input (potential attack attempt)
        if '[REDACTED]' in text:
            logger.warning(
                "potential_prompt_injection_detected",
                sanitized_text=text[:LOG_FIELD_MAX_LENGTH]
            )

        return text

    @staticmethod
    def _validate_learning_context(learning_context: Dict) -> Dict:
        """
        Validate and sanitize learning context data.

        Args:
            learning_context: Learning data dictionary

        Returns:
            Validated and sanitized learning context

        Raises:
            ValueError: If learning context structure is invalid
        """
        if not learning_context:
            return {}

        if not isinstance(learning_context, dict):
            logger.error(
                "invalid_learning_context_type",
                context_type=type(learning_context).__name__
            )
            raise ValueError(f"learning_context must be dict, got {type(learning_context)}")

        # Validate expected fields and types
        validated = {}

        # Validate high_value_issue_types (list of strings)
        if 'high_value_issue_types' in learning_context:
            high_value = learning_context['high_value_issue_types']
            if isinstance(high_value, list):
                # Sanitize each issue type string
                validated['high_value_issue_types'] = [
                    PromptFactory._sanitize_user_input(
                        str(item),
                        PromptFactory.MAX_ISSUE_TYPE_LENGTH
                    )
                    for item in high_value[:10]  # Limit to 10 items
                    if item
                ]

        # Validate low_value_issue_types (list of strings)
        if 'low_value_issue_types' in learning_context:
            low_value = learning_context['low_value_issue_types']
            if isinstance(low_value, list):
                validated['low_value_issue_types'] = [
                    PromptFactory._sanitize_user_input(
                        str(item),
                        PromptFactory.MAX_ISSUE_TYPE_LENGTH
                    )
                    for item in low_value[:10]  # Limit to 10 items
                    if item
                ]

        # Validate positive_feedback_rate (float between 0 and 1)
        if 'positive_feedback_rate' in learning_context:
            rate = learning_context['positive_feedback_rate']
            if isinstance(rate, (int, float)) and 0.0 <= rate <= 1.0:
                validated['positive_feedback_rate'] = float(rate)
            else:
                logger.warning(
                    "invalid_positive_feedback_rate",
                    rate=rate
                )

        # Validate total_feedback_count (non-negative integer)
        if 'total_feedback_count' in learning_context:
            count = learning_context['total_feedback_count']
            if isinstance(count, int) and count >= 0:
                validated['total_feedback_count'] = count
            else:
                logger.warning(
                    "invalid_total_feedback_count",
                    count=count
                )

        return validated
    
    def build_single_pass_prompt(
        self,
        files: List[FileChange],
        pr_title: str,
        learning_context: Dict
    ) -> str:
        """
        Build prompt for single-pass review (small PRs).

        Args:
            files: All changed files
            pr_title: PR title
            learning_context: Learning data from past reviews

        Returns:
            Complete prompt for AI
        """
        # Validate inputs
        if not files:
            logger.warning("build_single_pass_prompt_called_with_empty_files")
            raise ValueError("files list cannot be empty")

        # Sanitize user-controlled inputs
        safe_pr_title = self._sanitize_user_input(pr_title, self.MAX_TITLE_LENGTH)
        safe_learning_context = self._validate_learning_context(learning_context)

        prompt_parts = []

        # Header (sanitized)
        prompt_parts.append(f"# Pull Request Review: {safe_pr_title}")
        prompt_parts.append("")
        prompt_parts.append("Review the following Infrastructure as Code changes.")
        prompt_parts.append("")

        # Add learning context if available (Phase 2 implementation)
        if safe_learning_context:
            learning_section = self._build_learning_context_section(safe_learning_context)
            if learning_section:
                prompt_parts.append(learning_section)
                prompt_parts.append("")

        # Add each file's changes
        for file in files:
            # Sanitize file path
            safe_path = self._sanitize_user_input(file.path, self.MAX_PATH_LENGTH)
            prompt_parts.append(f"## File: {safe_path}")
            prompt_parts.append(f"**Type:** {file.file_type}")
            prompt_parts.append("")

            # Add formatted diff sections
            for section in file.changed_sections:
                formatted = self.diff_parser.format_section_for_review(section)
                prompt_parts.append(formatted)
                prompt_parts.append("")

        # Add review instructions
        prompt_parts.append("---")
        prompt_parts.append("")
        prompt_parts.append(self._get_review_instructions(files))
        prompt_parts.append("")
        prompt_parts.append(self._get_response_format())

        return "\n".join(prompt_parts)
    
    def build_group_prompt(
        self,
        files: List[FileChange],
        learning_context: Dict
    ) -> str:
        """
        Build prompt for reviewing a group of related files.

        Args:
            files: Group of related files
            learning_context: Learning data

        Returns:
            Prompt for this file group
        """
        # Similar to single-pass but for a subset
        if not files:
            logger.warning("build_group_prompt_called_with_empty_files")
            return ""

        # Validate learning context
        safe_learning_context = self._validate_learning_context(learning_context)

        file_type = files[0].file_type

        prompt_parts = []
        prompt_parts.append(f"# Review: {file_type} Files")
        prompt_parts.append("")

        for file in files:
            # Sanitize file path
            safe_path = self._sanitize_user_input(file.path, self.MAX_PATH_LENGTH)
            prompt_parts.append(f"## {safe_path}")
            for section in file.changed_sections:
                formatted = self.diff_parser.format_section_for_review(section)
                prompt_parts.append(formatted)
                prompt_parts.append("")

        prompt_parts.append("---")
        prompt_parts.append(self._get_review_instructions(files))
        prompt_parts.append(self._get_response_format())

        return "\n".join(prompt_parts)
    
    def build_file_prompt(
        self,
        file: FileChange,
        learning_context: Dict
    ) -> str:
        """
        Build prompt for reviewing a single file.

        Args:
            file: Single file to review
            learning_context: Learning data

        Returns:
            Prompt for this file
        """
        # Validate learning context
        safe_learning_context = self._validate_learning_context(learning_context)

        prompt_parts = []

        # Sanitize file path
        safe_path = self._sanitize_user_input(file.path, self.MAX_PATH_LENGTH)
        prompt_parts.append(f"# Review: {safe_path}")
        prompt_parts.append(f"**Type:** {file.file_type}")
        prompt_parts.append("")

        for section in file.changed_sections:
            formatted = self.diff_parser.format_section_for_review(section)
            prompt_parts.append(formatted)
            prompt_parts.append("")

        prompt_parts.append("---")
        prompt_parts.append(self._get_review_instructions([file]))
        prompt_parts.append(self._get_response_format())

        return "\n".join(prompt_parts)
    
    def build_cross_file_prompt(self, results: List) -> str:
        """
        Build prompt for cross-file dependency analysis.

        Args:
            results: List of ReviewResult objects with critical issues

        Returns:
            Prompt for cross-file analysis
        """
        if not results:
            logger.warning("build_cross_file_prompt_called_with_empty_results")
            return ""

        prompt_parts = []

        prompt_parts.append("# Cross-File Dependency Analysis")
        prompt_parts.append("")
        prompt_parts.append("The following files have critical or high-severity issues:")
        prompt_parts.append("")

        for result in results:
            # Sanitize PR ID (convert to string and sanitize)
            safe_pr_id = self._sanitize_user_input(str(result.pr_id), 50)
            prompt_parts.append(f"## PR {safe_pr_id}")

            if hasattr(result, 'issues') and result.issues:
                for issue in result.issues:
                    if hasattr(issue, 'is_critical_or_high') and issue.is_critical_or_high:
                        # Sanitize file path and message
                        safe_file_path = self._sanitize_user_input(
                            issue.file_path,
                            self.MAX_PATH_LENGTH
                        )
                        safe_message = self._sanitize_user_input(
                            issue.message,
                            self.MAX_MESSAGE_LENGTH
                        )
                        prompt_parts.append(f"- {safe_file_path}: {safe_message}")

        prompt_parts.append("")
        prompt_parts.append("Analyze potential dependencies and cascading impacts.")
        prompt_parts.append("")
        prompt_parts.append("Return JSON with:")
        prompt_parts.append('{"analysis": "description of cross-file impacts"}')

        return "\n".join(prompt_parts)
    
    def _get_review_instructions(self, files: List[FileChange]) -> str:
        """
        Get review instructions based on file types.
        
        Args:
            files: Files being reviewed
            
        Returns:
            Review instructions
        """
        file_types = set(f.file_type for f in files)
        
        instructions = ["## Review Instructions", ""]
        
        instructions.append("Focus on:")
        instructions.append("1. **Security**: Exposed endpoints, hardcoded secrets, weak permissions")
        instructions.append("2. **Best Practices**: Resource naming, tags, configuration")
        instructions.append("3. **Reliability**: Error handling, retries, timeouts")
        instructions.append("4. **Cost Optimization**: Unnecessary resources, oversized instances")
        instructions.append("")
        
        # Add file-type specific instructions
        if FileType.TERRAFORM in file_types:
            instructions.append("**Terraform-specific:**")
            instructions.append("- Check for public endpoints without firewall rules")
            instructions.append("- Verify state backend configuration")
            instructions.append("- Look for missing required tags")
            instructions.append("")
        
        if FileType.ANSIBLE in file_types:
            instructions.append("**Ansible-specific:**")
            instructions.append("- Check for hardcoded passwords/secrets")
            instructions.append("- Verify idempotency")
            instructions.append("- Look for missing error handling")
            instructions.append("")
        
        if FileType.PIPELINE in file_types:
            instructions.append("**Pipeline-specific:**")
            instructions.append("- Check for secure variable usage")
            instructions.append("- Verify approval gates for production")
            instructions.append("- Look for missing error handling")
            instructions.append("")
        
        if FileType.JSON in file_types:
            instructions.append("**JSON Configuration-specific:**")
            instructions.append("- Validate JSON structure and syntax")
            instructions.append("- Check for hardcoded secrets or sensitive data")
            instructions.append("- Verify proper use of environment variables")
            instructions.append("- Look for configuration best practices")
            instructions.append("")
        
        return "\n".join(instructions)
    
    def _get_response_format(self) -> str:
        """Get required JSON response format with suggested fixes."""
        return """## Response Format

Respond with valid JSON only:

```json
{
  "issues": [
    {
      "severity": "critical|high|medium|low|info",
      "file_path": "/path/to/file.tf",
      "line_number": 10,
      "issue_type": "PublicEndpoint",
      "message": "Clear description of the issue",
      "suggestion": "How to fix it",
      "suggested_fix": {
        "description": "Brief description of the fix",
        "before": "code_that_has_the_issue",
        "after": "fixed_code_snippet",
        "explanation": "Why this fix works"
      }
    }
  ],
  "recommendation": "approve|request_changes|comment",
  "summary": "Overall assessment (1-2 sentences)"
}
```

**Important:**
- severity must be: critical, high, medium, low, or info
- recommendation must be: approve, request_changes, or comment
- line_number should be 0 if file-level issue
- **Always include suggested_fix for critical and high severity issues**
- suggested_fix.before should show the problematic code
- suggested_fix.after should show the corrected code
- Focus on actionable, specific feedback with working code fixes
- Avoid generic advice - provide copy-pasteable solutions
"""

    def _build_learning_context_section(self, learning_context: Dict) -> Optional[str]:
        """
        Build the learning context section for prompts.

        Integrates team feedback to guide AI review focus:
        - Prioritizes high-value issue types (frequently accepted by team)
        - De-prioritizes low-value issue types (frequently rejected)
        - Provides context on team preferences

        Args:
            learning_context: Dictionary from FeedbackTracker.get_learning_context()
                Should be pre-validated by _validate_learning_context()
                Expected structure:
                {
                    "high_value_issue_types": ["SecretExposed", "PublicEndpoint"],
                    "low_value_issue_types": ["MinorStyle"],
                    "positive_feedback_rate": 0.85,
                    "total_feedback_count": 150,
                    "issue_type_stats": {...}
                }

        Returns:
            Formatted learning context section, or None if insufficient data
        """
        if not learning_context:
            return None

        total_feedback = learning_context.get('total_feedback_count', 0)

        # Require minimum feedback for statistical significance
        if total_feedback < 5:
            logger.debug(
                "insufficient_feedback_for_learning",
                total_feedback=total_feedback,
                minimum_required=5
            )
            return None

        high_value = learning_context.get('high_value_issue_types', [])
        low_value = learning_context.get('low_value_issue_types', [])
        positive_rate = learning_context.get('positive_feedback_rate', 0.0)

        section_parts = ["## Team Preferences (Based on Past Feedback)", ""]

        # Add positive feedback context
        if positive_rate > 0:
            # Sanitize the rate display (already validated to be 0-1)
            section_parts.append(
                f"Team acceptance rate: {positive_rate:.0%} "
                f"(based on {total_feedback} feedback entries)"
            )
            section_parts.append("")

        # High-value issue types - prioritize these
        # Note: issue types are already sanitized by _validate_learning_context
        if high_value:
            section_parts.append("**High-Priority Issues (Team Values These):**")
            section_parts.append(
                "Focus on these issue types - the team frequently acts on them:"
            )
            for issue_type in high_value[:5]:  # Top 5
                section_parts.append(f"- {issue_type}")
            section_parts.append("")

        # Low-value issue types - de-prioritize
        # Note: issue types are already sanitized by _validate_learning_context
        if low_value:
            section_parts.append("**Low-Priority Issues (Team Often Ignores):**")
            section_parts.append(
                "De-prioritize or skip these - the team rarely acts on them:"
            )
            for issue_type in low_value[:3]:  # Top 3
                section_parts.append(f"- {issue_type}")
            section_parts.append("")

        # Add guidance based on feedback
        if high_value or low_value:
            section_parts.append("**Guidance:**")
            if high_value:
                section_parts.append(
                    "- Spend more effort on detailed analysis of high-priority issues"
                )
            if low_value:
                section_parts.append(
                    "- Only report low-priority issues if they are critical or high severity"
                )
            section_parts.append("")

        # Return None if no meaningful content generated
        if len(section_parts) <= 2:
            return None

        logger.info(
            "learning_context_added_to_prompt",
            high_value_count=len(high_value),
            low_value_count=len(low_value),
            total_feedback=total_feedback
        )

        return "\n".join(section_parts)
