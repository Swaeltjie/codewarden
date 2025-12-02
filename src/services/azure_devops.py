# src/services/azure_devops.py
"""
Azure DevOps REST API Client

Handles all interactions with Azure DevOps REST API including:
- Pull request details
- File diffs
- Posting comments (summary and inline)

Authentication:
- Azure AD Managed Identity (credential-free)

Reliability:
- Circuit breaker protection
- Connection pool tuning

Version: 2.5.10 - Centralized logging usage
"""
import aiohttp
import asyncio
from typing import Dict, List, Optional
from functools import lru_cache
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)
from azure.identity.aio import DefaultAzureCredential

from src.utils.config import get_secret_manager, get_settings
from src.services.circuit_breaker import CircuitBreakerManager, CircuitBreakerError
from src.utils.constants import (
    AZURE_DEVOPS_TIMEOUT,
    DEFAULT_CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    DEFAULT_CIRCUIT_BREAKER_TIMEOUT_SECONDS,
    DEFAULT_RETRY_AFTER_SECONDS,
    MAX_COMMENT_LENGTH,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


class DevOpsAuthError(Exception):
    """Authentication failed with Azure DevOps."""
    pass


class DevOpsRateLimitError(Exception):
    """Rate limit exceeded."""
    def __init__(self, message: str, retry_after: int = DEFAULT_RETRY_AFTER_SECONDS):
        super().__init__(message)
        self.retry_after = retry_after


class AzureDevOpsClient:
    """
    Client for Azure DevOps REST API v7.1.

    Authentication:
    - Uses Azure AD Managed Identity (credential-free)
    - Requires Managed Identity to be added to Azure DevOps organization
    - Requires appropriate permissions (Code: Read, PR Threads: Contribute)
    """

    # Azure DevOps resource ID for Azure AD authentication
    AZURE_DEVOPS_RESOURCE = "https://app.vssps.visualstudio.com/.default"

    def __init__(self):
        """
        Initialize Azure DevOps client with Managed Identity authentication.

        Requires:
        - Managed Identity enabled on Azure Function App
        - MI added to Azure DevOps organization with Basic license
        - Project permissions: Code (Read), PR Threads (Contribute)
        """
        self.settings = get_settings()
        self.base_url = f"https://dev.azure.com/{self.settings.AZURE_DEVOPS_ORG}"
        self.api_version = "7.1"
        self._session: Optional[aiohttp.ClientSession] = None
        self._session_lock = asyncio.Lock()
        self._credential: Optional[DefaultAzureCredential] = None

    async def _get_auth_token(self) -> str:
        """
        Get authentication token using Managed Identity.

        Returns:
            Authorization header value with Bearer token

        Raises:
            DevOpsAuthError: If authentication fails
        """
        try:
            # Initialize credential if needed
            if self._credential is None:
                self._credential = DefaultAzureCredential()

            # Get Azure AD token for Azure DevOps
            token = await self._credential.get_token(self.AZURE_DEVOPS_RESOURCE)

            logger.info(
                "devops_auth_success",
                method="managed_identity",
                expires_on=token.expires_on
            )

            return f"Bearer {token.token}"

        except Exception as e:
            logger.error(
                "devops_auth_failed",
                error=str(e),
                error_type=type(e).__name__
            )
            raise DevOpsAuthError(
                "Failed to authenticate to Azure DevOps using Managed Identity. "
                "Ensure the Function App's Managed Identity is:\n"
                "1. Added to your Azure DevOps organization (with Basic license)\n"
                "2. Granted appropriate permissions (Code: Read, PR Threads: Contribute)\n"
                "3. Added to the specific project"
            ) from e

    async def _get_session(self) -> aiohttp.ClientSession:
        """
        Lazy-initialized HTTP session with authentication.
        Thread-safe session initialization with asyncio.Lock.
        """
        # Fast path: session already initialized
        if self._session is not None and not self._session.closed:
            # Get fresh token and update headers (tokens expire after ~1 hour)
            try:
                auth_header = await self._get_auth_token()
                self._session.headers.update({"Authorization": auth_header})
                return self._session
            except Exception:
                # If token refresh fails, need to reinitialize under lock
                # Don't close here - will be handled in the lock section
                pass

        if self._session is None or self._session.closed:
            # Slow path: need to initialize session
            async with self._session_lock:
                # Double-check after acquiring lock
                if self._session is None or self._session.closed:
                    # Clean up old session if it exists and is closed
                    if self._session is not None and self._session.closed:
                        try:
                            await self._session.close()
                        except Exception:
                            pass  # Already closed
                        self._session = None

                    auth_header = await self._get_auth_token()

                    # Connection pool tuning for production workloads
                    # - limit: Max simultaneous connections (Azure DevOps can handle 100+)
                    # - limit_per_host: Max connections per host (prevent overwhelming single endpoint)
                    # - ttl_dns_cache: Cache DNS for 5 minutes (reduce DNS lookups)
                    # - enable_cleanup_closed: Clean up closed connections automatically
                    connector = aiohttp.TCPConnector(
                        limit=100,           # Total connection pool size
                        limit_per_host=30,   # Per-host limit for Azure DevOps
                        ttl_dns_cache=300,   # DNS cache TTL (5 minutes)
                        enable_cleanup_closed=True
                    )

                    self._session = aiohttp.ClientSession(
                        connector=connector,
                        headers={
                            "Authorization": auth_header,
                            "Content-Type": "application/json",
                            "Accept": "application/json"
                        },
                        timeout=aiohttp.ClientTimeout(total=AZURE_DEVOPS_TIMEOUT)
                    )

                    logger.info(
                        "devops_session_created",
                        auth_method="managed_identity"
                    )

        return self._session

    # REMOVED in v2.5.0: Deprecated sync `session` property
    # All callers should use `await _get_session()` instead
    # The property was removed because:
    # 1. It could not reliably guarantee a valid session
    # 2. Synchronous access to an async resource is error-prone
    # 3. All production code now uses _get_session()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(aiohttp.ClientError),
        reraise=True
    )
    async def get_pull_request_details(
        self,
        project_id: str,
        repository_id: str,
        pr_id: int
    ) -> Dict:
        """
        Get detailed information about a pull request.

        Retries up to 3 times with exponential backoff on transient errors.

        Args:
            project_id: Project UUID or name
            repository_id: Repository UUID
            pr_id: Pull request ID

        Returns:
            PR details including title, description, files, etc.

        Raises:
            DevOpsAuthError: If authentication fails
            DevOpsRateLimitError: If rate limited
        """
        url = (
            f"{self.base_url}/{project_id}/_apis/git/repositories/"
            f"{repository_id}/pullRequests/{pr_id}"
            f"?api-version={self.api_version}"
        )
        
        logger.info(
            "devops_get_pr_details",
            project_id=project_id,
            repository_id=repository_id,
            pr_id=pr_id
        )

        # Get circuit breaker for Azure DevOps
        breaker = await CircuitBreakerManager.get_breaker(
            service_name="azure_devops",
            failure_threshold=DEFAULT_CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            timeout_seconds=DEFAULT_CIRCUIT_BREAKER_TIMEOUT_SECONDS
        )

        # Define API call function
        async def make_api_call():
            session = await self._get_session()
            async with session.get(url) as response:
                if response.status == 401:
                    raise DevOpsAuthError("Authentication failed - check Managed Identity permissions")
                elif response.status == 429:
                    retry_after = int(response.headers.get('Retry-After', DEFAULT_RETRY_AFTER_SECONDS))
                    raise DevOpsRateLimitError(
                        "Rate limit exceeded",
                        retry_after=retry_after
                    )

                response.raise_for_status()
                data = await response.json()

                logger.info(
                    "devops_pr_details_fetched",
                    pr_id=pr_id,
                    title=data.get('title')
                )

                return data

        try:
            # Execute with circuit breaker protection
            return await breaker.call(make_api_call)

        except CircuitBreakerError as e:
            logger.error(
                "azure_devops_circuit_breaker_open",
                error=str(e),
                pr_id=pr_id
            )
            raise Exception(f"Azure DevOps temporarily unavailable: {str(e)}")
                
        except aiohttp.ClientError as e:
            logger.error("devops_api_error", error=str(e), url=url)
            raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(aiohttp.ClientError),
        reraise=True
    )
    async def get_pull_request_files(
        self,
        project_id: str,
        repository_id: str,
        pr_id: int
    ) -> List[Dict]:
        """
        Get list of changed files in a pull request.

        Retries up to 3 times with exponential backoff on transient errors.

        Args:
            project_id: Project UUID or name
            repository_id: Repository UUID
            pr_id: Pull request ID

        Returns:
            List of file changes with metadata
        """
        # Get iterations to find commits
        url = (
            f"{self.base_url}/{project_id}/_apis/git/repositories/"
            f"{repository_id}/pullRequests/{pr_id}/iterations"
            f"?api-version={self.api_version}"
        )
        
        session = await self._get_session()
        async with session.get(url) as response:
            response.raise_for_status()
            iterations = await response.json()
        
        if not iterations.get('value'):
            return []
        
        # Get the latest iteration
        latest_iteration = iterations['value'][-1]
        iteration_id = latest_iteration['id']
        
        # Get changes in this iteration
        url = (
            f"{self.base_url}/{project_id}/_apis/git/repositories/"
            f"{repository_id}/pullRequests/{pr_id}/iterations/{iteration_id}/changes"
            f"?api-version={self.api_version}"
        )
        
        session = await self._get_session()
        async with session.get(url) as response:
            response.raise_for_status()
            data = await response.json()

        return data.get('changeEntries', [])
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(aiohttp.ClientError),
        reraise=True
    )
    async def get_file_diff(
        self,
        repository_id: str,
        file_path: str,
        source_commit: str,
        target_commit: str
    ) -> str:
        """
        Get unified diff for a specific file between two commits.

        Retries up to 3 times with exponential backoff on transient errors.

        Args:
            repository_id: Repository UUID
            file_path: Path to file (e.g., /main.tf)
            source_commit: Source commit SHA (feature branch)
            target_commit: Target commit SHA (main branch)

        Returns:
            Unified diff string
        """
        # Azure DevOps API for diffs - get detailed diff with diffContentType
        url = (
            f"{self.base_url}/_apis/git/repositories/{repository_id}/diffs/commits"
            f"?baseVersion={target_commit}&targetVersion={source_commit}"
            f"&diffContentType=unified&api-version={self.api_version}"
        )

        logger.debug(
            "devops_get_file_diff",
            file_path=file_path,
            source=source_commit[:8],
            target=target_commit[:8]
        )

        try:
            session = await self._get_session()
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.json()

            # Find the specific file in the changes
            for change in data.get('changes', []):
                item_path = change.get('item', {}).get('path', '')

                if item_path == file_path or item_path.endswith(file_path):
                    # Convert Azure DevOps diff to unified diff format
                    return self._format_as_unified_diff(change, file_path, repository_id, source_commit, target_commit)

            logger.warning("file_not_found_in_diff", file_path=file_path)
            return ""

        except Exception as e:
            logger.error(
                "diff_fetch_failed",
                file_path=file_path,
                error=str(e)
            )
            return ""

    async def _get_file_content(
        self,
        repository_id: str,
        file_path: str,
        commit_sha: str
    ) -> Optional[str]:
        """
        Get file content at a specific commit.

        Args:
            repository_id: Repository UUID
            file_path: Path to file
            commit_sha: Commit SHA

        Returns:
            File content as string, or None if file doesn't exist
        """
        url = (
            f"{self.base_url}/_apis/git/repositories/{repository_id}/items"
            f"?path={file_path}&versionType=commit&version={commit_sha}"
            f"&api-version={self.api_version}"
        )

        try:
            session = await self._get_session()
            async with session.get(url) as response:
                if response.status == 404:
                    return None
                response.raise_for_status()
                # Response is the raw file content
                return await response.text()
        except Exception as e:
            logger.warning(
                "file_content_fetch_failed",
                file_path=file_path,
                commit=commit_sha[:8],
                error=str(e)
            )
            return None

    def _format_as_unified_diff(
        self,
        change: Dict,
        file_path: str,
        repository_id: str,
        source_commit: str,
        target_commit: str
    ) -> str:
        """
        Convert Azure DevOps change format to unified diff format.

        Azure DevOps API returns diffs in a proprietary format with 'blocks' containing
        line-by-line changes. This method converts it to standard unified diff format
        compatible with git and standard diff parsers.

        Unified diff format structure:
        - Header: diff --git a/file b/file
        - File markers: --- a/file, +++ b/file
        - Hunks: @@ -start,count +start,count @@
        - Lines: " " (context), "-" (removed), "+" (added)

        Azure DevOps block structure:
        - blocks[]: Array of change blocks
        - Each block has:
          - oLine, oLinesCount: Original file line position and count
          - mLine, mLinesCount: Modified file line position and count
          - changeType: 0=unchanged, 1=added, 2=deleted, 3=modified
          - oLines[]: Original lines (for deleted/modified)
          - mLines[]: Modified lines (for added/modified/context)

        Args:
            change: Change object from Azure DevOps API
            file_path: Path to the file (e.g., "/main.tf")
            repository_id: Repository UUID (unused, for future enhancement)
            source_commit: Source commit SHA (unused, for future enhancement)
            target_commit: Target commit SHA (unused, for future enhancement)

        Returns:
            Unified diff string compatible with standard diff parsers
        """
        change_type = change.get('changeType', 'edit')

        # Step 1: Build unified diff header (git format)
        diff_lines = [
            f"diff --git a{file_path} b{file_path}",
        ]

        # Step 2: Add file mode headers based on change type
        # New files need special markers for diff parsers
        if change_type in ['add', 'add, edit']:
            # File was added - no previous version exists
            diff_lines.append("new file mode 100644")
            diff_lines.append("--- /dev/null")  # No original file
            diff_lines.append(f"+++ b{file_path}")  # New file in target
        elif change_type in ['delete']:
            # File was deleted - no new version exists
            diff_lines.append("deleted file mode 100644")
            diff_lines.append(f"--- a{file_path}")  # Original file
            diff_lines.append("+++ /dev/null")  # No new file
        else:
            # File was modified - both versions exist
            diff_lines.append(f"--- a{file_path}")  # Original version (-)
            diff_lines.append(f"+++ b{file_path}")  # Modified version (+)

        # Step 3: Extract change count dictionary (fallback data)
        # This contains aggregate counts when detailed blocks aren't available
        change_counts = change.get('changeCountDictionary', {})

        # Step 4: Process diff content - two paths:
        # Path A: Detailed 'blocks' available (preferred)
        # Path B: Only summary counts available (fallback)

        if 'blocks' in change:
            # ===== PATH A: Process detailed line-by-line changes =====
            # Each block represents a "hunk" in unified diff terminology

            for block in change['blocks']:
                # Extract line position information
                # Azure DevOps uses 'm' prefix for Modified (new) file
                # and 'o' prefix for Original (old) file
                modified_lines_start = block.get('mLine', 1)  # New file start line
                modified_lines_count = block.get('mLinesCount', 0)  # New file line count
                original_lines_start = block.get('oLine', 1)  # Old file start line
                original_lines_count = block.get('oLinesCount', 0)  # Old file line count

                # Create hunk header in unified diff format
                # Format: @@ -old_start,old_count +new_start,new_count @@
                # Example: @@ -10,5 +12,7 @@ means:
                #   - Old file: 5 lines starting at line 10
                #   - New file: 7 lines starting at line 12
                hunk_header = (
                    f"@@ -{original_lines_start},{original_lines_count} "
                    f"+{modified_lines_start},{modified_lines_count} @@"
                )
                diff_lines.append(hunk_header)

                # Process the actual line changes
                # changeType in block indicates what happened to these lines
                change_type_block = block.get('changeType', 0)

                # Azure DevOps changeType values:
                # 0 = Unchanged (context lines)
                # 1 = Added (only in new file)
                # 2 = Deleted (only in old file)
                # 3 = Modified (changed from old to new)

                if change_type_block == 1:
                    # Lines were added (only exist in new file)
                    # Prefix with '+' in unified diff
                    if 'mLines' in block:
                        for line in block['mLines']:
                            diff_lines.append(f"+{line.get('content', '')}")

                elif change_type_block == 2:
                    # Lines were deleted (only exist in old file)
                    # Prefix with '-' in unified diff
                    if 'oLines' in block:
                        for line in block['oLines']:
                            diff_lines.append(f"-{line.get('content', '')}")

                elif change_type_block == 3:
                    # Lines were modified (exist in both, but different)
                    # Show old lines with '-', then new lines with '+'
                    if 'oLines' in block:
                        for line in block['oLines']:
                            diff_lines.append(f"-{line.get('content', '')}")
                    if 'mLines' in block:
                        for line in block['mLines']:
                            diff_lines.append(f"+{line.get('content', '')}")

                else:
                    # Unchanged context lines (changeType == 0 or unknown)
                    # Prefix with ' ' (space) in unified diff
                    # These provide context around changes
                    if 'mLines' in block:
                        for line in block['mLines']:
                            diff_lines.append(f" {line.get('content', '')}")

        else:
            # ===== PATH B: Fallback when detailed blocks aren't available =====
            # Create a simplified diff showing only change counts
            # This happens when Azure DevOps API doesn't return full diff content

            if change_type in ['add', 'add, edit']:
                # File was added - show single hunk with add count
                add_count = change_counts.get('Add', 1)
                diff_lines.append(f"@@ -0,0 +1,{add_count} @@")
                # Placeholder since we don't have actual content
                diff_lines.append("+[New file - content not available in API response]")

            elif change_type == 'delete':
                # File was deleted - show single hunk with delete count
                delete_count = change_counts.get('Delete', 1)
                diff_lines.append(f"@@ -1,{delete_count} +0,0 @@")
                # Placeholder since we don't have actual content
                diff_lines.append("-[Deleted file - content not available in API response]")

            else:
                # File was edited - show combined change counts
                add_count = change_counts.get('Add', 0)  # Lines added
                edit_count = change_counts.get('Edit', 0)  # Lines modified
                delete_count = change_counts.get('Delete', 0)  # Lines removed
                total_changes = add_count + edit_count + delete_count

                if total_changes > 0:
                    # Create hunk showing approximate old and new line counts
                    # Use max(1, ...) to avoid @@ -0,0 +0,0 @@ which is invalid
                    old_count = max(1, delete_count + edit_count)
                    new_count = max(1, add_count + edit_count)
                    diff_lines.append(f"@@ -1,{old_count} +1,{new_count} @@")

                    # Show summary placeholders since we don't have actual lines
                    diff_lines.append(f"-[{delete_count + edit_count} lines changed/removed]")
                    diff_lines.append(f"+[{add_count + edit_count} lines changed/added]")

        # Step 5: Join all lines with newlines to create final unified diff
        return "\n".join(diff_lines)
    
    async def post_pr_comment(
        self,
        project_id: str,
        repository_id: str,
        pr_id: int,
        comment: str,
        thread_type: str = "summary"
    ) -> Dict:
        """
        Post a summary comment thread to PR.

        Args:
            project_id: Project UUID or name
            repository_id: Repository UUID
            pr_id: Pull request ID
            comment: Comment text (markdown supported)
            thread_type: Type of thread (summary, discussion)

        Returns:
            Created thread object

        Raises:
            ValueError: If comment exceeds max length (64KB for Azure DevOps API)
        """
        # Azure DevOps has a 64KB limit on comment content
        if len(comment) > MAX_COMMENT_LENGTH:
            logger.warning(
                "comment_too_long",
                pr_id=pr_id,
                length=len(comment),
                max_length=MAX_COMMENT_LENGTH
            )
            # Truncate comment with warning
            comment = comment[:MAX_COMMENT_LENGTH - 100] + "\n\n... (Comment truncated due to length limit)"

        url = (
            f"{self.base_url}/{project_id}/_apis/git/repositories/"
            f"{repository_id}/pullRequests/{pr_id}/threads"
            f"?api-version={self.api_version}"
        )

        payload = {
            "comments": [
                {
                    "parentCommentId": 0,
                    "content": comment,
                    "commentType": 1  # 1 = text, 2 = code change
                }
            ],
            "status": 1,  # 1 = active, 2 = fixed, 3 = won't fix, 4 = closed
            "properties": {
                "Microsoft.TeamFoundation.Discussion.SupportsMarkdown": {
                    "$type": "System.Int32",
                    "$value": 1
                }
            }
        }
        
        logger.info(
            "devops_posting_comment",
            pr_id=pr_id,
            thread_type=thread_type,
            comment_length=len(comment)
        )

        try:
            session = await self._get_session()
            async with session.post(url, json=payload) as response:
                response.raise_for_status()
                result = await response.json()
                
                logger.info(
                    "devops_comment_posted",
                    pr_id=pr_id,
                    thread_id=result.get('id')
                )
                
                return result
                
        except Exception as e:
            logger.error(
                "comment_post_failed",
                pr_id=pr_id,
                error=str(e)
            )
            raise
    
    async def post_inline_comment(
        self,
        project_id: str,
        repository_id: str,
        pr_id: int,
        file_path: str,
        line_number: int,
        comment: str
    ) -> Dict:
        """
        Post an inline comment on a specific line in a file.
        
        Args:
            project_id: Project UUID or name
            repository_id: Repository UUID
            pr_id: Pull request ID
            file_path: Path to file (e.g., /main.tf)
            line_number: Line number (1-indexed)
            comment: Comment text (markdown supported)
            
        Returns:
            Created thread object
        """
        url = (
            f"{self.base_url}/{project_id}/_apis/git/repositories/"
            f"{repository_id}/pullRequests/{pr_id}/threads"
            f"?api-version={self.api_version}"
        )
        
        payload = {
            "comments": [
                {
                    "parentCommentId": 0,
                    "content": comment,
                    "commentType": 1
                }
            ],
            "status": 1,
            "threadContext": {
                "filePath": file_path,
                "rightFileStart": {
                    "line": line_number,
                    "offset": 1
                },
                "rightFileEnd": {
                    "line": line_number,
                    "offset": 999  # End of line
                }
            },
            "properties": {
                "Microsoft.TeamFoundation.Discussion.SupportsMarkdown": {
                    "$type": "System.Int32",
                    "$value": 1
                }
            }
        }
        
        logger.info(
            "devops_posting_inline_comment",
            pr_id=pr_id,
            file_path=file_path,
            line_number=line_number
        )
        
        try:
            session = await self._get_session()
            async with session.post(url, json=payload) as response:
                response.raise_for_status()
                result = await response.json()

                logger.info(
                    "devops_inline_comment_posted",
                    pr_id=pr_id,
                    thread_id=result.get('id')
                )
                
                return result
                
        except Exception as e:
            logger.error(
                "inline_comment_post_failed",
                pr_id=pr_id,
                file_path=file_path,
                line_number=line_number,
                error=str(e)
            )
            raise

    async def _get_pr_threads(
        self,
        project_id: str,
        repository_id: str,
        pr_id: int
    ) -> List[Dict]:
        """
        Get all comment threads for a PR.

        Used by feedback tracker to analyze developer feedback.

        Args:
            project_id: Project UUID or name
            repository_id: Repository UUID
            pr_id: Pull request ID

        Returns:
            List of thread objects with comments and status
        """
        url = (
            f"{self.base_url}/{project_id}/_apis/git/repositories/"
            f"{repository_id}/pullRequests/{pr_id}/threads"
            f"?api-version={self.api_version}"
        )

        logger.info(
            "devops_fetching_pr_threads",
            pr_id=pr_id,
            project_id=project_id
        )

        try:
            session = await self._get_session()
            async with session.get(url) as response:
                if response.status == 404:
                    logger.warning("pr_threads_not_found", pr_id=pr_id)
                    return []

                response.raise_for_status()
                data = await response.json()

                threads = data.get('value', [])

                logger.info(
                    "devops_pr_threads_fetched",
                    pr_id=pr_id,
                    thread_count=len(threads)
                )

                return threads

        except Exception as e:
            logger.error(
                "pr_threads_fetch_failed",
                pr_id=pr_id,
                error=str(e)
            )
            # Return empty list on error - don't fail feedback collection
            return []

    async def close(self):
        """Close the HTTP session and credential."""
        # Use lock to prevent concurrent close calls
        async with self._session_lock:
            if self._session and not self._session.closed:
                try:
                    await self._session.close()
                    logger.debug("devops_session_closed")
                except Exception as e:
                    logger.warning("devops_session_close_error", error=str(e))
                finally:
                    self._session = None

            if self._credential:
                try:
                    await self._credential.close()
                    logger.debug("devops_credential_closed")
                except Exception as e:
                    logger.warning("devops_credential_close_error", error=str(e))
                finally:
                    self._credential = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
        return False  # Don't suppress exceptions
