# src/services/context_manager.py
"""
Context Manager for Review Strategy Selection

Determines which review strategy to use based on PR size and complexity.

Version: 2.6.0 - Universal code review with registry-based token estimates
"""
from enum import Enum
from typing import Dict, List

from src.models.pr_event import FileChange, FileType
from src.services.file_type_registry import FileTypeRegistry, FileCategory
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

    v2.6.0: Uses FileTypeRegistry for dynamic token estimates
    supporting 40+ file categories.
    """

    def __init__(self) -> None:
        # Token estimates are now fetched from the registry
        # This is kept for backward compatibility but uses registry internally
        pass
    
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
        # Small PRs: review everything in one AI call
        if file_count <= 5 and estimated_tokens <= 10_000:
            strategy = ReviewStrategy.SINGLE_PASS
        # Medium PRs: group related files and review each group
        elif file_count <= 15 and estimated_tokens <= 40_000:
            strategy = ReviewStrategy.CHUNKED
        # Large PRs: review each file individually, then cross-file analysis
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

        v2.6.0: Uses FileTypeRegistry for category-specific base estimates,
        then adjusts based on actual changed sections.

        Args:
            file: FileChange object

        Returns:
            Estimated token count
        """
        # Get base estimate from registry based on file category
        base_estimate = FileTypeRegistry.get_token_estimate(file.file_type)

        # If we have parsed changed sections, use those for more accurate estimate
        if file.changed_sections and len(file.changed_sections) > 0:
            total_lines = sum(
                len(section.context_before) +
                len(section.removed_lines) +
                len(section.added_lines) +
                len(section.context_after)
                for section in file.changed_sections
            )
            # Estimate: ~6 tokens per line
            line_based_estimate = total_lines * 6

            # Use the larger of base estimate or line-based estimate
            return max(base_estimate, line_based_estimate)

        # Fallback: use total changes or base estimate
        changes_estimate = max(0, file.total_changes * 6)
        return max(base_estimate, changes_estimate)
    
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
