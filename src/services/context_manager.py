# src/services/context_manager.py
"""
Context Manager for Review Strategy Selection

Determines which review strategy to use based on PR size and complexity.

Version: 2.5.12 - Comprehensive type hints
"""
from enum import Enum
from typing import Dict, List

from src.models.pr_event import FileChange, FileType
from src.utils.logging import get_logger

logger = get_logger(__name__)


class ReviewStrategy(str, Enum):
    """Review strategy based on PR size."""
    SINGLE_PASS = "single_pass"    # Small PRs: ≤5 files, review all at once
    CHUNKED = "chunked"             # Medium PRs: 6-15 files, group related files
    HIERARCHICAL = "hierarchical"   # Large PRs: >15 files, individual + cross-file


class ContextManager:
    """
    Manages review context and determines optimal strategy.
    
    Simplified version for MVP - uses basic file count heuristics.
    """
    
    def __init__(self) -> None:
        # Token estimates per file type (average)
        self.token_estimates: Dict[FileType, int] = {
            FileType.TERRAFORM: 300,
            FileType.ANSIBLE: 400,
            FileType.PIPELINE: 350,
            FileType.JSON: 400
        }
    
    def determine_strategy(self, files: List[FileChange]) -> ReviewStrategy:
        """
        Determine optimal review strategy for PR.
        
        Criteria:
        - Small (≤5 files, ≤10K tokens): SINGLE_PASS
        - Medium (6-15 files, ≤40K tokens): CHUNKED
        - Large (>15 files or >40K tokens): HIERARCHICAL
        
        Args:
            files: List of changed files
            
        Returns:
            ReviewStrategy enum
        """
        file_count = len(files)
        
        # Estimate total tokens
        estimated_tokens = sum(
            self._estimate_file_tokens(f) for f in files
        )
        
        logger.info(
            "strategy_evaluation",
            file_count=file_count,
            estimated_tokens=estimated_tokens
        )
        
        # Simple heuristics for MVP
        if file_count <= 5 and estimated_tokens <= 10_000:
            strategy = ReviewStrategy.SINGLE_PASS
        elif file_count <= 15 and estimated_tokens <= 40_000:
            strategy = ReviewStrategy.CHUNKED
        else:
            strategy = ReviewStrategy.HIERARCHICAL
        
        logger.info(
            "strategy_determined",
            strategy=strategy.value,
            file_count=file_count,
            estimated_tokens=estimated_tokens
        )
        
        return strategy
    
    def _estimate_file_tokens(self, file: FileChange) -> int:
        """
        Estimate token count for a file.

        Uses changed sections for diff-only analysis estimate.

        Args:
            file: FileChange object

        Returns:
            Estimated token count
        """
        # If we have parsed changed sections, use those
        if file.changed_sections and len(file.changed_sections) > 0:
            total_lines = sum(
                len(section.context_before) +
                len(section.removed_lines) +
                len(section.added_lines) +
                len(section.context_after)
                for section in file.changed_sections
            )
            # Estimate: ~6 tokens per line
            return total_lines * 6

        # Fallback: use total changes
        return max(0, file.total_changes * 6)
    
    def group_related_files(self, files: List[FileChange]) -> List[List[FileChange]]:
        """
        Group related files for chunked review.
        
        Simplified MVP version: groups by file type.
        
        Args:
            files: List of FileChange objects
            
        Returns:
            List of file groups
        """
        # Group by file type
        groups = {}
        for file in files:
            file_type = file.file_type
            if file_type not in groups:
                groups[file_type] = []
            groups[file_type].append(file)
        
        # Convert to list of groups
        grouped = list(groups.values())
        
        logger.info(
            "files_grouped",
            total_files=len(files),
            group_count=len(grouped),
            groups={
                str(ft): len(g) for ft, g in groups.items()
            }
        )
        
        return grouped
