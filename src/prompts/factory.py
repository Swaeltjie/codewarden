# src/prompts/factory.py
"""
Prompt Factory for AI Code Reviews

Generates specialized prompts for different file types and review strategies.

Version: 2.4.0 - Implemented Phase 2 learning context integration
"""
from typing import List, Dict, Optional
from src.models.pr_event import FileChange, FileType
from src.services.diff_parser import DiffParser
import structlog

logger = structlog.get_logger(__name__)


class PromptFactory:
    """
    Generates AI review prompts for different scenarios.
    
    Creates specialized prompts for:
    - Different file types (Terraform, Ansible, etc.)
    - Different review strategies (single-pass, chunked, hierarchical)
    - Learning context integration
    """
    
    def __init__(self):
        self.diff_parser = DiffParser()
    
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
        prompt_parts = []
        
        # Header
        prompt_parts.append(f"# Pull Request Review: {pr_title}")
        prompt_parts.append("")
        prompt_parts.append("Review the following Infrastructure as Code changes.")
        prompt_parts.append("")
        
        # Add learning context if available (Phase 2 implementation)
        if learning_context:
            learning_section = self._build_learning_context_section(learning_context)
            if learning_section:
                prompt_parts.append(learning_section)
                prompt_parts.append("")
        
        # Add each file's changes
        for file in files:
            prompt_parts.append(f"## File: {file.path}")
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
            return ""
        
        file_type = files[0].file_type
        
        prompt_parts = []
        prompt_parts.append(f"# Review: {file_type} Files")
        prompt_parts.append("")
        
        for file in files:
            prompt_parts.append(f"## {file.path}")
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
        prompt_parts = []
        
        prompt_parts.append(f"# Review: {file.path}")
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
        prompt_parts = []
        
        prompt_parts.append("# Cross-File Dependency Analysis")
        prompt_parts.append("")
        prompt_parts.append("The following files have critical or high-severity issues:")
        prompt_parts.append("")
        
        for result in results:
            prompt_parts.append(f"## {result.pr_id}")
            for issue in result.issues:
                if issue.is_critical_or_high:
                    prompt_parts.append(f"- {issue.file_path}: {issue.message}")
        
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
            section_parts.append(
                f"Team acceptance rate: {positive_rate:.0%} "
                f"(based on {total_feedback} feedback entries)"
            )
            section_parts.append("")

        # High-value issue types - prioritize these
        if high_value:
            section_parts.append("**High-Priority Issues (Team Values These):**")
            section_parts.append(
                "Focus on these issue types - the team frequently acts on them:"
            )
            for issue_type in high_value[:5]:  # Top 5
                section_parts.append(f"- {issue_type}")
            section_parts.append("")

        # Low-value issue types - de-prioritize
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
