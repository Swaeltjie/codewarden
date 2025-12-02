# src/services/diff_parser.py
"""
Git Diff Parser with Diff-Only Analysis

Parses git diffs to extract only changed sections, dramatically reducing
token usage and improving review focus.

Version: 2.5.12 - Comprehensive type hints
"""
from typing import List, Optional
from dataclasses import dataclass
import unidiff

from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ChangedSection:
    """Represents a section of changed code with context."""
    
    file_path: str
    old_start_line: int
    new_start_line: int
    context_before: List[str]
    removed_lines: List[str]
    added_lines: List[str]
    context_after: List[str]
    
    @property
    def total_lines(self) -> int:
        """Total lines in this section including context."""
        return (
            len(self.context_before) +
            len(self.removed_lines) +
            len(self.added_lines) +
            len(self.context_after)
        )
    
    @property
    def changed_lines_count(self) -> int:
        """Count of actually changed lines (added + removed)."""
        return len(self.removed_lines) + len(self.added_lines)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "file_path": self.file_path,
            "old_start_line": self.old_start_line,
            "new_start_line": self.new_start_line,
            "context_before": self.context_before,
            "removed_lines": self.removed_lines,
            "added_lines": self.added_lines,
            "context_after": self.context_after,
            "total_lines": self.total_lines,
            "changed_lines_count": self.changed_lines_count
        }


class DiffParser:
    """
    Parses git diffs to extract only changed sections.
    
    This class implements diff-only analysis, which reduces token usage by
    50-85% compared to reviewing entire files.
    """
    
    def __init__(self, context_lines: int = 3) -> None:
        """
        Initialize diff parser.

        Args:
            context_lines: Number of context lines before/after changes
        """
        self.context_lines: int = context_lines
    
    async def parse_diff(self, diff_content: str) -> List[ChangedSection]:
        """
        Parse a git diff and extract changed sections with context.
        
        Args:
            diff_content: Raw git diff content
            
        Returns:
            List of ChangedSection objects
            
        Raises:
            ValueError: If diff content is invalid
        """
        if not diff_content or not diff_content.strip():
            logger.warning("empty_diff_content")
            return []
        
        try:
            # Parse diff using unidiff library
            patch_set = unidiff.PatchSet(diff_content)
            
            sections = []
            for patched_file in patch_set:
                file_sections = self._extract_file_sections(patched_file)
                sections.extend(file_sections)
            
            logger.info(
                "diff_parsed",
                total_sections=len(sections),
                total_changed_lines=sum(s.changed_lines_count for s in sections),
                files_affected=len(patch_set)
            )
            
            return sections
            
        except unidiff.errors.UnidiffParseError as e:
            logger.error(
                "diff_parse_failed",
                error=str(e),
                diff_preview=diff_content[:200]
            )
            raise ValueError(f"Invalid diff format: {e}")
    
    def _extract_file_sections(
        self,
        patched_file: unidiff.PatchedFile
    ) -> List[ChangedSection]:
        """
        Extract changed sections from a single file.
        
        Args:
            patched_file: Parsed file from unidiff
            
        Returns:
            List of ChangedSection objects for this file
        """
        sections = []
        
        # Get file path (handle both source and target)
        file_path = patched_file.path or patched_file.source_file
        
        for hunk in patched_file:
            section = self._process_hunk(hunk, file_path)
            if section:
                sections.append(section)
        
        return sections
    
    def _process_hunk(
        self,
        hunk: unidiff.Hunk,
        file_path: str
    ) -> Optional[ChangedSection]:
        """
        Process a single hunk and extract changed section with context.

        Args:
            hunk: Diff hunk from unidiff
            file_path: Path to the file

        Returns:
            ChangedSection if changes found, None otherwise
        """
        context_before = []
        removed_lines = []
        added_lines = []
        context_after = []

        # Track if we're before, during, or after changes
        found_change = False
        lines_after_change = 0

        # Safety limit: prevent processing extremely large hunks (DoS protection)
        MAX_HUNK_LINES = 10000
        line_count = 0

        for line in hunk:
            line_count += 1
            if line_count > MAX_HUNK_LINES:
                logger.warning(
                    "hunk_too_large",
                    file_path=file_path,
                    line_count=line_count,
                    max_allowed=MAX_HUNK_LINES
                )
                break
            if line.is_context:
                if not found_change:
                    # Context before changes
                    context_before.append(line.value)
                    # Keep only last N context lines
                    if len(context_before) > self.context_lines:
                        context_before.pop(0)
                else:
                    # Context after changes
                    if lines_after_change < self.context_lines:
                        context_after.append(line.value)
                        lines_after_change += 1
            
            elif line.is_removed:
                found_change = True
                # Safety limit on removed lines (DoS protection)
                if len(removed_lines) < MAX_HUNK_LINES // 2:
                    removed_lines.append(line.value)
                lines_after_change = 0  # Reset counter

            elif line.is_added:
                found_change = True
                # Safety limit on added lines (DoS protection)
                if len(added_lines) < MAX_HUNK_LINES // 2:
                    added_lines.append(line.value)
                lines_after_change = 0  # Reset counter
        
        # Only return section if changes were found
        if not found_change:
            return None
        
        return ChangedSection(
            file_path=file_path,
            old_start_line=hunk.source_start,
            new_start_line=hunk.target_start,
            context_before=context_before,
            removed_lines=removed_lines,
            added_lines=added_lines,
            context_after=context_after
        )
    
    def format_section_for_review(self, section: ChangedSection) -> str:
        """
        Format a changed section for AI review.
        
        Args:
            section: ChangedSection to format
            
        Returns:
            Formatted string for AI prompt
        """
        lines = []
        
        lines.append(f"File: {section.file_path}")
        lines.append(f"Lines: {section.new_start_line}-{section.new_start_line + section.total_lines}")
        lines.append("")
        
        # Context before
        if section.context_before:
            lines.append("Context before:")
            for line in section.context_before:
                lines.append(f"  {line.rstrip()}")
            lines.append("")
        
        # Removed lines
        if section.removed_lines:
            lines.append("Removed:")
            for line in section.removed_lines:
                lines.append(f"- {line.rstrip()}")
            lines.append("")
        
        # Added lines
        if section.added_lines:
            lines.append("Added:")
            for line in section.added_lines:
                lines.append(f"+ {line.rstrip()}")
            lines.append("")
        
        # Context after
        if section.context_after:
            lines.append("Context after:")
            for line in section.context_after:
                lines.append(f"  {line.rstrip()}")
        
        return "\n".join(lines)
    
    def calculate_token_estimate(self, sections: List[ChangedSection]) -> int:
        """
        Estimate token count for changed sections.
        
        Args:
            sections: List of changed sections
            
        Returns:
            Estimated token count
        """
        total_chars = sum(
            section.total_lines * 80  # Assume avg 80 chars per line
            for section in sections
        )
        
        # Rough estimate: 4 characters per token
        return total_chars // 4
    
    def calculate_savings(
        self,
        sections: List[ChangedSection],
        total_file_lines: int
    ) -> dict:
        """
        Calculate token savings from diff-only analysis.
        
        Args:
            sections: Changed sections
            total_file_lines: Total lines in all files
            
        Returns:
            Dictionary with savings metrics
        """
        reviewed_lines = sum(s.total_lines for s in sections)
        changed_lines = sum(s.changed_lines_count for s in sections)
        
        tokens_with_diff_only = self.calculate_token_estimate(sections)
        tokens_full_files = (total_file_lines * 80) // 4
        
        savings_percent = (
            (tokens_full_files - tokens_with_diff_only) * 100.0 / tokens_full_files
            if tokens_full_files > 0 else 0.0
        )
        
        return {
            "total_file_lines": total_file_lines,
            "reviewed_lines": reviewed_lines,
            "changed_lines": changed_lines,
            "tokens_full_files": tokens_full_files,
            "tokens_diff_only": tokens_with_diff_only,
            "tokens_saved": tokens_full_files - tokens_with_diff_only,
            "savings_percent": round(savings_percent, 1)
        }


# Example usage and testing
async def example_usage() -> None:
    """Example of how to use DiffParser."""
    
    sample_diff = """
diff --git a/main.tf b/main.tf
index 1234567..abcdefg 100644
--- a/main.tf
+++ b/main.tf
@@ -45,8 +45,10 @@ resource "azurerm_kubernetes_cluster" "aks" {
   name                = "my-aks"
   location            = azurerm_resource_group.rg.location
   
-  api_server_access_profile {
-    authorized_ip_ranges = ["0.0.0.0/0"]
+  api_server_access_profile {
+    authorized_ip_ranges = [
+      "10.0.0.0/8",
+      "192.168.1.0/24"
+    ]
   }
 }
"""
    
    parser = DiffParser()
    sections = await parser.parse_diff(sample_diff)
    
    for section in sections:
        print(parser.format_section_for_review(section))
        print(f"\nToken estimate: {parser.calculate_token_estimate([section])}")
    
    # Calculate savings
    savings = parser.calculate_savings(sections, total_file_lines=500)
    print(f"\nSavings: {savings['savings_percent']}%")
    print(f"Tokens: {savings['tokens_full_files']} → {savings['tokens_diff_only']}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(example_usage())
