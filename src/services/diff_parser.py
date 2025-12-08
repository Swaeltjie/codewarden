# src/services/diff_parser.py
"""
Git Diff Parser with Diff-Only Analysis

Parses git diffs to extract only changed sections, dramatically reducing
token usage and improving review focus.

Version: 2.6.26 - Fallback parser for unidiff compatibility
"""
from typing import List, Optional
from dataclasses import dataclass
import unidiff

from src.utils.constants import MAX_HUNK_LINES
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
            logger.warning(
                "unidiff_parse_failed_using_fallback",
                error=str(e),
                diff_preview=diff_content[:200]
            )
            # v2.6.26: Fallback to manual parsing when unidiff fails
            # This handles generated diffs that unidiff is strict about
            return self._fallback_parse_diff(diff_content)
    
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
    
    def _fallback_parse_diff(self, diff_content: str) -> List[ChangedSection]:
        """
        Fallback diff parser when unidiff fails.

        Handles generated diffs that unidiff is strict about (e.g., hunk line counts).
        This parser is more lenient and focuses on extracting the essential change info.

        Args:
            diff_content: Raw git diff content

        Returns:
            List of ChangedSection objects
        """
        sections = []
        current_file = None
        current_added = []
        current_removed = []
        current_context_before = []
        current_context_after = []
        in_hunk = False
        found_change = False
        new_start_line = 1
        old_start_line = 1

        lines = diff_content.split('\n')

        for line in lines:
            # Detect file header
            if line.startswith('diff --git'):
                # Save previous section if exists
                if current_file and (current_added or current_removed):
                    sections.append(ChangedSection(
                        file_path=current_file,
                        old_start_line=old_start_line,
                        new_start_line=new_start_line,
                        context_before=current_context_before[-self.context_lines:],
                        removed_lines=current_removed,
                        added_lines=current_added,
                        context_after=current_context_after[:self.context_lines]
                    ))

                # Reset for new file
                current_added = []
                current_removed = []
                current_context_before = []
                current_context_after = []
                in_hunk = False
                found_change = False
                new_start_line = 1
                old_start_line = 1

                # Extract file path from diff header
                # Format: diff --git a/path/to/file b/path/to/file
                parts = line.split(' ')
                if len(parts) >= 4:
                    # Use the b/ path (target file)
                    current_file = parts[-1]
                    if current_file.startswith('b/'):
                        current_file = current_file[2:]
                continue

            # Detect new file in --- line
            if line.startswith('--- '):
                continue

            # Detect new file in +++ line
            if line.startswith('+++ '):
                if current_file is None:
                    path = line[4:].strip()
                    if path.startswith('b/'):
                        path = path[2:]
                    if path != '/dev/null':
                        current_file = path
                continue

            # Detect hunk header
            if line.startswith('@@'):
                in_hunk = True
                # Parse line numbers: @@ -old_start,old_count +new_start,new_count @@
                try:
                    parts = line.split(' ')
                    if len(parts) >= 3:
                        new_part = parts[2]  # +new_start,new_count or +new_start
                        if new_part.startswith('+'):
                            new_part = new_part[1:]
                            if ',' in new_part:
                                new_start_line = int(new_part.split(',')[0])
                            else:
                                new_start_line = int(new_part)

                        old_part = parts[1]  # -old_start,old_count or -old_start
                        if old_part.startswith('-'):
                            old_part = old_part[1:]
                            if ',' in old_part:
                                old_start_line = int(old_part.split(',')[0])
                            else:
                                old_start_line = int(old_part)
                except (ValueError, IndexError):
                    pass
                continue

            # Skip metadata lines
            if line.startswith('new file mode') or line.startswith('index '):
                continue

            # Skip "no newline" marker
            if line.startswith('\\ No newline'):
                continue

            # Process diff content
            if in_hunk:
                if line.startswith('+'):
                    found_change = True
                    current_added.append(line[1:] + '\n')
                    current_context_after = []  # Reset after context
                elif line.startswith('-'):
                    found_change = True
                    current_removed.append(line[1:] + '\n')
                    current_context_after = []  # Reset after context
                elif line.startswith(' ') or line == '':
                    content = line[1:] + '\n' if line.startswith(' ') else '\n'
                    if not found_change:
                        current_context_before.append(content)
                    else:
                        current_context_after.append(content)

        # Save final section
        if current_file and (current_added or current_removed):
            sections.append(ChangedSection(
                file_path=current_file,
                old_start_line=old_start_line,
                new_start_line=new_start_line,
                context_before=current_context_before[-self.context_lines:],
                removed_lines=current_removed,
                added_lines=current_added,
                context_after=current_context_after[:self.context_lines]
            ))

        logger.info(
            "fallback_diff_parsed",
            total_sections=len(sections),
            total_changed_lines=sum(s.changed_lines_count for s in sections)
        )

        return sections

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
