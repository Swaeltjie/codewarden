# src/services/context_manager.py
"""
Context Manager for Review Strategy Selection

Determines which review strategy to use based on PR size and complexity.

Version: 2.7.2 - Added defensive validation for empty files and malformed data
"""
from enum import Enum
from typing import Dict, List

from src.models.pr_event import FileChange, FileType
from src.services.file_type_registry import FileTypeRegistry, FileCategory
from src.utils.constants import (
    MAX_LINES_PER_FILE,
    MAX_TOKENS_PER_FILE,
    STRATEGY_SMALL_FILE_LIMIT,
    STRATEGY_SMALL_TOKEN_LIMIT,
    STRATEGY_MEDIUM_FILE_LIMIT,
    STRATEGY_MEDIUM_TOKEN_LIMIT,
    TOKENS_PER_LINE_ESTIMATE,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


class ReviewStrategy(str, Enum):
    """Review strategy based on PR size."""

    SINGLE_PASS = "single_pass"  # Small PRs: ≤5 files, review all at once
    CHUNKED = "chunked"  # Medium PRs: 6-15 files, group related files
    HIERARCHICAL = "hierarchical"  # Large PRs: >15 files, individual + cross-file


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
        # Validate input - return safe default for empty PRs
        if not files:
            logger.warning("empty_files_list_provided")
            return ReviewStrategy.SINGLE_PASS

        file_count = len(files)

        # Estimate total tokens
        estimated_tokens = sum(self._estimate_file_tokens(f) for f in files)

        logger.info(
            "strategy_evaluation",
            file_count=file_count,
            estimated_tokens=estimated_tokens,
        )

        # Simple heuristics for MVP
        # Small PRs: review everything in one AI call
        if (
            file_count <= STRATEGY_SMALL_FILE_LIMIT
            and estimated_tokens <= STRATEGY_SMALL_TOKEN_LIMIT
        ):
            strategy = ReviewStrategy.SINGLE_PASS
        # Medium PRs: group related files and review each group
        elif (
            file_count <= STRATEGY_MEDIUM_FILE_LIMIT
            and estimated_tokens <= STRATEGY_MEDIUM_TOKEN_LIMIT
        ):
            strategy = ReviewStrategy.CHUNKED
        # Large PRs: review each file individually, then cross-file analysis
        else:
            strategy = ReviewStrategy.HIERARCHICAL

        logger.info(
            "strategy_determined",
            strategy=strategy.value,
            file_count=file_count,
            estimated_tokens=estimated_tokens,
        )

        return strategy

    def _estimate_file_tokens(self, file: FileChange) -> int:
        """
        Estimate token count for a file.

        v2.6.0: Uses FileTypeRegistry for category-specific base estimates,
        then adjusts based on actual changed sections.
        v2.6.1: Added bounds checking to prevent integer overflow.

        Args:
            file: FileChange object

        Returns:
            Estimated token count (capped at MAX_TOKENS_PER_FILE)
        """
        # Get base estimate from registry based on file category
        base_estimate = FileTypeRegistry.get_token_estimate(file.file_type)

        # If we have parsed changed sections, use those for more accurate estimate
        if file.changed_sections and len(file.changed_sections) > 0:
            try:
                total_lines = sum(
                    len(section.context_before)
                    + len(section.removed_lines)
                    + len(section.added_lines)
                    + len(section.context_after)
                    for section in file.changed_sections
                )

                # v2.6.1: Apply bounds checking to prevent overflow
                if total_lines > MAX_LINES_PER_FILE:
                    logger.warning(
                        "excessive_line_count",
                        total_lines=total_lines,
                        max_lines=MAX_LINES_PER_FILE,
                        file_path=file.path[:100] if file.path else "unknown",
                    )
                    total_lines = MAX_LINES_PER_FILE

                # Estimate: ~6 tokens per line (capped)
                line_based_estimate = min(
                    total_lines * TOKENS_PER_LINE_ESTIMATE, MAX_TOKENS_PER_FILE
                )

                # Use the larger of base estimate or line-based estimate
                return max(base_estimate, line_based_estimate)
            except (AttributeError, TypeError) as e:
                logger.warning(
                    "invalid_changed_sections",
                    error=str(e),
                    file_path=file.path[:100] if file.path else "unknown",
                )
                # Fall through to fallback calculation

        # Fallback: use total changes or base estimate (with bounds)
        try:
            changes_estimate = min(
                max(0, file.total_changes * TOKENS_PER_LINE_ESTIMATE),
                MAX_TOKENS_PER_FILE,
            )
        except (AttributeError, TypeError):
            changes_estimate = 0
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
        # Handle empty input
        if not files:
            return []

        # Group by file type with defensive handling
        groups: Dict[FileCategory, List[FileChange]] = {}
        for file in files:
            try:
                file_type = file.file_type
                # Validate it's a proper FileCategory
                if not isinstance(file_type, FileCategory):
                    logger.warning(
                        "invalid_file_type_for_grouping",
                        file_path=file.path[:100] if file.path else "unknown",
                        file_type=str(file_type),
                    )
                    file_type = FileCategory.GENERIC  # Fallback

                if file_type not in groups:
                    groups[file_type] = []
                groups[file_type].append(file)
            except Exception as e:
                logger.warning(
                    "failed_to_group_file",
                    error=str(e),
                    file_path=(
                        file.path[:100]
                        if hasattr(file, "path") and file.path
                        else "unknown"
                    ),
                )
                # Add to generic group as fallback
                if FileCategory.GENERIC not in groups:
                    groups[FileCategory.GENERIC] = []
                groups[FileCategory.GENERIC].append(file)

        # Convert to list of groups
        grouped = list(groups.values())

        logger.info(
            "files_grouped",
            total_files=len(files),
            group_count=len(grouped),
            groups={str(ft): len(g) for ft, g in groups.items()},
        )

        return grouped
