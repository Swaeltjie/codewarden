# src/handlers/pr_webhook.py
"""
Pull Request Webhook Handler

Orchestrates the entire PR review workflow:
1. Check request idempotency (prevent duplicates)
2. Fetch PR details and changed files
3. Parse diffs (diff-only analysis)
4. Determine review strategy
5. Check response cache for identical diffs
6. Call AI for review (with circuit breaker protection)
7. Cache review responses
8. Post results back to Azure DevOps

Version: 2.5.12 - Comprehensive type hints
"""
import asyncio
from typing import List, Optional, Tuple
from datetime import datetime, timezone

from src.models.pr_event import PREvent, FileChange, FileType
from src.models.review_result import ReviewResult, ReviewIssue
from src.models.feedback import ReviewHistoryEntity
from src.services.azure_devops import AzureDevOpsClient
from src.services.diff_parser import DiffParser
from src.services.ai_client import AIClient
from src.services.feedback_tracker import FeedbackTracker
from src.services.context_manager import ContextManager, ReviewStrategy
from src.services.idempotency_checker import IdempotencyChecker
from src.services.response_cache import ResponseCache
from src.prompts.factory import PromptFactory
from src.utils.config import get_settings
from src.utils.table_storage import get_table_client, ensure_table_exists
from src.utils.logging import get_logger

logger = get_logger(__name__)


class PRWebhookHandler:
    """Handles incoming PR webhook events and orchestrates reviews."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.devops_client: Optional[AzureDevOpsClient] = None
        self.ai_client: Optional[AIClient] = None
        self.diff_parser = DiffParser()
        self.feedback_tracker = FeedbackTracker()
        self.context_manager = ContextManager()
        self.prompt_factory = PromptFactory()
        self.idempotency_checker = IdempotencyChecker()
        self.response_cache = ResponseCache()  # Uses configurable TTL from settings
        self.dry_run: bool = False  # When True, skips posting comments to Azure DevOps

        # Concurrency limiter for parallel operations (v2.5.0)
        self._review_semaphore = asyncio.Semaphore(self.settings.MAX_CONCURRENT_REVIEWS)

    async def __aenter__(self) -> "PRWebhookHandler":
        """Async context manager entry - initialize resources."""
        try:
            self.devops_client = await AzureDevOpsClient().__aenter__()
            self.ai_client = await AIClient().__aenter__()
            return self
        except Exception:
            # Clean up any partially initialized resources
            if self.devops_client:
                await self.devops_client.close()
            raise

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Async context manager exit - cleanup resources."""
        if self.devops_client:
            await self.devops_client.close()
        if self.ai_client:
            await self.ai_client.close()
        return False
    
    async def handle_pr_event(self, pr_event: PREvent) -> ReviewResult:
        """
        Main entry point for handling a PR event.
        
        Args:
            pr_event: Parsed PR event from Azure DevOps
            
        Returns:
            ReviewResult with findings and recommendations
        """
        start_time = datetime.now(timezone.utc)

        # Bind context to logger for this request
        request_logger = logger.bind(
            pr_id=pr_event.pr_id,
            repository=pr_event.repository_name
        )

        request_logger.info("pr_review_started")

        try:
            # Step 0: Check for duplicate request (idempotency)
            is_duplicate, previous_result = await self.idempotency_checker.is_duplicate_request(
                pr_id=pr_event.pr_id,
                repository=pr_event.repository_name,
                project=pr_event.project_name,
                event_type=pr_event.event_type,
                source_commit_id=pr_event.source_commit_id
            )

            if is_duplicate:
                request_logger.info(
                    "duplicate_request_ignored",
                    previous_result=previous_result
                )
                return ReviewResult.create_empty(
                    pr_id=pr_event.pr_id,
                    message=f"Duplicate request - already processed. Previous result: {previous_result}"
                )

            # Record this request as being processed
            await self.idempotency_checker.record_request(
                pr_id=pr_event.pr_id,
                repository=pr_event.repository_name,
                project=pr_event.project_name,
                event_type=pr_event.event_type,
                source_commit_id=pr_event.source_commit_id,
                result_summary="processing"
            )

            # Step 1: Fetch PR details
            pr_details = await self.devops_client.get_pull_request_details(
                project_id=pr_event.project_id,
                repository_id=pr_event.repository_id,
                pr_id=pr_event.pr_id
            )
            
            request_logger.info(
                "pr_details_fetched",
                title=pr_details.get('title'),
                file_count=len(pr_details.get('files', []))
            )

            # Step 2: Get changed files with diffs
            changed_files = await self._fetch_changed_files(pr_event, pr_details)

            if not changed_files:
                request_logger.info("no_iac_files_found")
                return ReviewResult.create_empty(
                    pr_id=pr_event.pr_id,
                    message="No IaC files found in this PR"
                )
            
            request_logger.info(
                "changed_files_classified",
                total_files=len(changed_files),
                terraform=sum(1 for f in changed_files if f.file_type == FileType.TERRAFORM),
                ansible=sum(1 for f in changed_files if f.file_type == FileType.ANSIBLE),
                pipeline=sum(1 for f in changed_files if f.file_type == FileType.PIPELINE),
                json=sum(1 for f in changed_files if f.file_type == FileType.JSON)
            )
            
            # Step 3: Parse diffs (diff-only analysis)
            for file in changed_files:
                file.changed_sections = await self.diff_parser.parse_diff(file.diff_content)
            
            total_changed_lines = sum(
                len(section.added_lines) + len(section.removed_lines)
                for file in changed_files
                for section in file.changed_sections
            )
            
            request_logger.info(
                "diffs_parsed",
                total_changed_lines=total_changed_lines,
                avg_per_file=round(total_changed_lines / len(changed_files), 2) if changed_files else 0
            )

            # Step 4: Determine review strategy
            strategy = self.context_manager.determine_strategy(changed_files)

            request_logger.info("review_strategy_determined", strategy=strategy.value)
            
            # Step 5: Get learning context (feedback from past reviews)
            learning_context = await self.feedback_tracker.get_learning_context(
                repository=pr_event.repository_name
            )
            
            # Step 6: Execute review based on strategy
            if strategy == ReviewStrategy.SINGLE_PASS:
                review_result = await self._single_pass_review(
                    changed_files, pr_event, learning_context
                )
            elif strategy == ReviewStrategy.CHUNKED:
                review_result = await self._chunked_review(
                    changed_files, pr_event, learning_context
                )
            else:  # HIERARCHICAL
                review_result = await self._hierarchical_review(
                    changed_files, pr_event, learning_context
                )
            
            # Step 7: Post results to Azure DevOps
            await self._post_review_results(pr_event, review_result)

            # Calculate duration
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            review_result.duration_seconds = duration

            # Step 8: Save review history for pattern detection
            await self._save_review_history(pr_event, pr_details, review_result, strategy)

            request_logger.info(
                "pr_review_completed",
                duration_seconds=duration,
                issues_found=len(review_result.issues),
                recommendation=review_result.recommendation
            )

            # Update idempotency record with final result
            await self.idempotency_checker.update_result(
                pr_id=pr_event.pr_id,
                repository=pr_event.repository_name,
                event_type=pr_event.event_type,
                source_commit_id=pr_event.source_commit_id,
                result_summary=f"{review_result.recommendation}: {len(review_result.issues)} issues"
            )

            return review_result
            
        except Exception as e:
            # Update idempotency record with failure status
            try:
                await self.idempotency_checker.update_result(
                    pr_id=pr_event.pr_id,
                    repository=pr_event.repository_name,
                    event_type=pr_event.event_type,
                    source_commit_id=pr_event.source_commit_id,
                    result_summary=f"FAILED: {type(e).__name__}: {str(e)[:100]}"
                )
            except Exception as update_error:
                request_logger.warning(
                    "idempotency_update_failed_after_error",
                    error=str(update_error),
                    original_error=str(e)
                )

            request_logger.exception(
                "pr_review_failed",
                error=str(e),
                error_type=type(e).__name__
            )
            raise
    
    async def _fetch_changed_files(
        self,
        pr_event: PREvent,
        pr_details: dict
    ) -> List[FileChange]:
        """
        Fetch changed files and filter for IaC files only.

        Uses semaphore-limited parallel fetching to prevent overwhelming
        Azure DevOps API while maintaining efficiency.

        Args:
            pr_event: PR event
            pr_details: PR details from DevOps

        Returns:
            List of FileChange objects (IaC files only)
        """
        all_files = pr_details.get('files', [])

        async def fetch_with_context(file_info: dict) -> Tuple[dict, str, Optional[Exception]]:
            """
            Fetch diff with error context preserved.

            Returns tuple of (file_info, diff_content, error) to preserve context.
            """
            async with self._review_semaphore:
                try:
                    diff = await self.devops_client.get_file_diff(
                        repository_id=pr_event.repository_id,
                        file_path=file_info['path'],
                        source_commit=pr_event.source_branch,
                        target_commit=pr_event.target_branch
                    )
                    return (file_info, diff, None)
                except Exception as e:
                    # Preserve error with context
                    return (file_info, "", e)

        # Fetch diffs in parallel with concurrency limiting
        results = await asyncio.gather(
            *[fetch_with_context(file) for file in all_files]
        )

        # Build FileChange objects and filter for IaC
        changed_files = []
        error_count = 0

        for file_info, diff_result, error in results:
            # Log failures with preserved context
            if error is not None:
                error_count += 1
                logger.warning(
                    "diff_fetch_failed",
                    file_path=file_info['path'],
                    error=str(error),
                    error_type=type(error).__name__
                )
                continue

            # Determine file type
            file_type = self._classify_file_type(file_info['path'])

            # Only include IaC files
            if file_type != FileType.UNKNOWN:
                changed_files.append(FileChange(
                    path=file_info['path'],
                    file_type=file_type,
                    diff_content=diff_result,
                    lines_added=file_info.get('linesAdded', 0),
                    lines_deleted=file_info.get('linesDeleted', 0)
                ))

        if error_count > 0:
            logger.warning(
                "diff_fetch_partial_failure",
                total_files=len(all_files),
                failed_count=error_count,
                success_count=len(all_files) - error_count
            )

        return changed_files
    
    def _classify_file_type(self, file_path: str) -> FileType:
        """
        Classify file based on path and extension.

        Args:
            file_path: Relative path to file

        Returns:
            FileType enum
        """
        # Check for excessively long paths (DoS protection)
        if len(file_path) > 2000:  # Match FileChange.path max_length
            logger.warning("file_path_too_long", path_length=len(file_path))
            return FileType.UNKNOWN

        # Sanitize file path to prevent path traversal
        if not self._is_safe_path(file_path):
            logger.warning("unsafe_file_path_detected", path=file_path)
            return FileType.UNKNOWN

        path_lower = file_path.lower()
        
        # Terraform
        if path_lower.endswith(('.tf', '.tfvars')):
            return FileType.TERRAFORM
        
        # YAML files - need to distinguish Ansible vs Pipelines
        if path_lower.endswith(('.yaml', '.yml')):
            # Pipeline indicators
            if any(x in path_lower for x in [
                'azure-pipelines',
                '.azuredevops',
                'pipelines/',
                '.azure-pipelines'
            ]):
                return FileType.PIPELINE
            
            # Ansible indicators
            if any(x in path_lower for x in [
                'ansible',
                'playbooks',
                'roles/',
                'playbook',
                'site.yml'
            ]):
                return FileType.ANSIBLE
            
            # Default YAML to Ansible (can be refined)
            return FileType.ANSIBLE
        
        # JSON configuration files
        if path_lower.endswith('.json'):
            # Exclude common non-IaC JSON files
            excluded_json = [
                'package.json',
                'package-lock.json',
                'tsconfig.json',
                'jsconfig.json',
                'settings.json',
                '.vscode/',
                'node_modules/',
                '.eslintrc.json',
                '.prettierrc.json'
            ]

            if any(x in path_lower for x in excluded_json):
                return FileType.UNKNOWN

            # All other JSON files are treated as configuration/IaC
            return FileType.JSON
        
        return FileType.UNKNOWN

    def _is_safe_path(self, file_path: str) -> bool:
        """
        Validate that a file path is safe and doesn't contain malicious patterns.

        Args:
            file_path: Path to validate

        Returns:
            True if safe, False otherwise
        """
        import os
        from pathlib import Path

        # Check for empty path
        if not file_path or not isinstance(file_path, str):
            return False

        # Check for null bytes
        if '\x00' in file_path:
            return False

        # Check for absolute paths (should be relative)
        if os.path.isabs(file_path):
            return False

        # Check for suspicious patterns BEFORE normalization
        # This prevents bypassing checks with encoded paths
        suspicious_patterns = [
            '../',
            '..\\',
            '/etc/',
            '/proc/',
            'c:\\',
            '\\windows\\',
        ]

        path_lower = file_path.lower()
        if any(pattern in path_lower for pattern in suspicious_patterns):
            return False

        # Normalize the path and check for traversal
        try:
            normalized = os.path.normpath(file_path)

            # Check for path traversal patterns
            if '..' in Path(normalized).parts:
                return False

            # Check if normalized path starts with / or \ (absolute)
            if normalized.startswith(('/', '\\')):
                return False

            # Additional check: ensure normalized path doesn't escape current directory
            # by checking that it doesn't start with parent directory references
            if normalized.startswith('..'):
                return False

        except (ValueError, OSError):
            return False

        return True

    async def _single_pass_review(
        self,
        files: List[FileChange],
        pr_event: PREvent,
        learning_context: dict
    ) -> ReviewResult:
        """Single-pass review for small PRs."""
        
        # Build prompt with all changed sections
        prompt = self.prompt_factory.build_single_pass_prompt(
            files=files,
            pr_title=pr_event.title,  # Use attribute, not .get()
            learning_context=learning_context
        )
        
        # Get AI review
        review_json = await self.ai_client.review_code(
            prompt=prompt,
            model=self.settings.OPENAI_MODEL
        )
        
        # Parse result
        return ReviewResult.from_ai_response(review_json, pr_event.pr_id)
    
    async def _chunked_review(
        self,
        files: List[FileChange],
        pr_event: PREvent,
        learning_context: dict
    ) -> ReviewResult:
        """Chunked review for medium PRs."""
        
        # Group related files
        file_groups = self.context_manager.group_related_files(files)
        
        # Review each group in parallel
        tasks = [
            self._review_file_group(group, pr_event, learning_context)
            for group in file_groups
        ]
        
        group_results = await asyncio.gather(*tasks)
        
        # Aggregate results
        return ReviewResult.aggregate(group_results, pr_event.pr_id)
    
    async def _hierarchical_review(
        self,
        files: List[FileChange],
        pr_event: PREvent,
        learning_context: dict
    ) -> ReviewResult:
        """Hierarchical review for large PRs with concurrency limiting."""

        async def review_with_semaphore(file: FileChange) -> Tuple[FileChange, ReviewResult, Optional[Exception]]:
            """Review single file with semaphore and error context preservation."""
            async with self._review_semaphore:
                try:
                    result = await self._review_single_file(
                        file, learning_context, repository=pr_event.repository_name
                    )
                    return (file, result, None)
                except Exception as e:
                    logger.warning(
                        "file_review_failed",
                        file_path=file.path,
                        error=str(e),
                        error_type=type(e).__name__
                    )
                    # Return empty result for failed file
                    return (file, ReviewResult.create_empty(pr_event.pr_id, f"Review failed: {str(e)}"), e)

        # Phase 1: Review each file individually with concurrency limiting
        results = await asyncio.gather(
            *[review_with_semaphore(file) for file in files]
        )

        # Extract individual results, logging any failures
        individual_results = []
        failed_count = 0
        for file, result, error in results:
            individual_results.append(result)
            if error is not None:
                failed_count += 1

        if failed_count > 0:
            logger.warning(
                "hierarchical_review_partial_failure",
                total_files=len(files),
                failed_count=failed_count
            )
        
        # Phase 2: Cross-file analysis (only files with issues)
        critical_files = [
            r for r in individual_results 
            if r.has_critical_issues()
        ]
        
        if critical_files:
            cross_file_analysis = await self._cross_file_analysis(
                critical_files, pr_event
            )
        else:
            cross_file_analysis = None
        
        # Phase 3: Aggregate
        return ReviewResult.hierarchical_aggregate(
            individual_results,
            cross_file_analysis,
            pr_event.pr_id
        )
    
    async def _review_file_group(
        self,
        file_group: List[FileChange],
        pr_event: PREvent,
        learning_context: dict
    ) -> ReviewResult:
        """Review a group of related files."""
        
        prompt = self.prompt_factory.build_group_prompt(
            files=file_group,
            learning_context=learning_context
        )
        
        review_json = await self.ai_client.review_code(prompt=prompt)
        return ReviewResult.from_ai_response(review_json, pr_event.pr_id)
    
    async def _review_single_file(
        self,
        file: FileChange,
        learning_context: dict,
        repository: Optional[str] = None
    ) -> ReviewResult:
        """
        Review a single file (diff-only) with response caching.

        Checks cache first to avoid redundant AI calls for identical diffs.
        """

        # Check cache if repository provided
        if repository and file.diff_content:
            cached_result = await self.response_cache.get_cached_review(
                repository=repository,
                diff_content=file.diff_content,
                file_path=file.path
            )

            if cached_result:
                logger.info(
                    "cache_hit_file_review",
                    file_path=file.path,
                    repository=repository
                )
                return cached_result

        # Cache miss - perform AI review
        prompt = self.prompt_factory.build_file_prompt(
            file=file,
            learning_context=learning_context
        )

        review_json = await self.ai_client.review_code(prompt=prompt)
        result = ReviewResult.from_ai_response(review_json, file_path=file.path)

        # Store in cache for future use
        if repository and file.diff_content:
            metadata = review_json.get('_metadata', {})
            await self.response_cache.cache_review(
                repository=repository,
                diff_content=file.diff_content,
                file_path=file.path,
                file_type=file.file_type.value if file.file_type else "unknown",
                review_result=result,
                tokens_used=metadata.get('tokens_used', 0),
                estimated_cost=metadata.get('estimated_cost', 0.0),
                model_used=metadata.get('model', 'unknown')
            )

            logger.info(
                "review_cached",
                file_path=file.path,
                repository=repository
            )

        return result
    
    async def _cross_file_analysis(
        self,
        critical_results: List[ReviewResult],
        pr_event: PREvent
    ) -> dict:
        """Analyze dependencies between files with issues."""
        
        prompt = self.prompt_factory.build_cross_file_prompt(
            results=critical_results
        )
        
        analysis = await self.ai_client.review_code(prompt=prompt)
        return {"analysis": analysis, "files_analyzed": len(critical_results)}
    
    async def _post_review_results(
        self,
        pr_event: PREvent,
        review_result: ReviewResult
    ) -> None:
        """Post review results as comments to Azure DevOps PR."""

        # Dry-run mode: skip posting, just log what would be posted
        if self.dry_run:
            inline_count = sum(1 for i in review_result.issues if i.severity in ["critical", "high"])
            logger.info(
                "dry_run_skip_posting",
                pr_id=pr_event.pr_id,
                issues_found=len(review_result.issues),
                inline_comments_would_post=inline_count,
                recommendation=review_result.recommendation
            )
            return

        # Format as markdown
        from src.services.comment_formatter import CommentFormatter

        formatter = CommentFormatter()

        # Main summary comment
        summary_markdown = formatter.format_summary(review_result)

        await self.devops_client.post_pr_comment(
            project_id=pr_event.project_id,
            repository_id=pr_event.repository_id,
            pr_id=pr_event.pr_id,
            comment=summary_markdown,
            thread_type="summary"
        )

        # Individual inline comments for high/critical issues
        for issue in review_result.issues:
            if issue.severity in ["critical", "high"]:
                inline_comment = formatter.format_inline_issue(issue)

                await self.devops_client.post_inline_comment(
                    project_id=pr_event.project_id,
                    repository_id=pr_event.repository_id,
                    pr_id=pr_event.pr_id,
                    file_path=issue.file_path,
                    line_number=issue.line_number,
                    comment=inline_comment
                )

        logger.info(
            "review_results_posted",
            pr_id=pr_event.pr_id,
            summary_posted=True,
            inline_comments=sum(1 for i in review_result.issues if i.severity in ["critical", "high"])
        )

    async def _save_review_history(
        self,
        pr_event: PREvent,
        pr_details: dict,
        review_result: ReviewResult,
        strategy: ReviewStrategy
    ) -> None:
        """
        Save review history to table storage for pattern detection.

        Args:
            pr_event: PR event data
            pr_details: PR details from Azure DevOps
            review_result: Review result to save
            strategy: Review strategy used
        """
        try:
            # Ensure table exists (moved inside try block for proper error handling)
            ensure_table_exists('reviewhistory')
            table_client = get_table_client('reviewhistory')

            # Create review history entity
            history_entity = ReviewHistoryEntity.from_review_result(
                review_result=review_result,
                pr_data={
                    'title': pr_details.get('title', 'Unknown'),
                    'author': pr_details.get('createdBy', {}).get('displayName', 'Unknown')
                },
                repository=pr_event.repository_name,
                project=pr_event.project_name
            )

            # Add strategy and AI model info
            history_entity.review_strategy = strategy.value
            history_entity.ai_model = self.settings.OPENAI_MODEL

            # Save to table storage
            table_client.upsert_entity(history_entity.to_table_entity())

            logger.info(
                "review_history_saved",
                review_id=review_result.review_id,
                repository=pr_event.repository_name,
                pr_id=pr_event.pr_id
            )

        except Exception as e:
            # Don't fail the review if history save fails
            logger.warning(
                "review_history_save_failed",
                error=str(e),
                error_type=type(e).__name__,
                pr_id=pr_event.pr_id
            )
