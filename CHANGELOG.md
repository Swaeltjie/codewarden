# Changelog

All notable changes to CodeWarden will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.7.4] - 2025-12-10

### Fixed - Models Reliability and Security

Comprehensive code review of all `src/models/` files with fixes for input validation, security, and data integrity.

**pr_event.py:**
- Added pre-compiled regex pattern for branch validation (performance)
- Added null byte validation to title, repository_name, project_name, event_type
- Enhanced email validation with domain check
- Added null byte validation to diff_content
- Fixed changed_sections type hint from `List` to `List[Any]`
- Made path traversal check platform-independent
- Moved `os` import to module level

**review_result.py:**
- Fixed overflow comparison: changed `>=` to `>` in token/cost aggregation
- Added type validation for metadata dict before extraction
- Added type coercion for tokens_used and estimated_cost with fallbacks
- Added INFO severity to summary counts (was missing from aggregate)

**feedback.py:**
- Added Azure Table Storage key validation (PartitionKey, RowKey)
- Added path traversal protection for file_path field
- Validates invalid characters in Table Storage keys (/, \, #, ?)

**reliability.py:**
- Added real date validation (not just format) for PartitionKey
- Added null byte validation for repository, project, event_type fields
- Added input validation for hash generation in create_request_id
- Added file_path security validation in CacheEntity
- Added path traversal check in create_content_hash

## [2.7.3] - 2025-12-10

### Fixed - Handler Reliability and Security

Comprehensive code review of `src/handlers/` files with fixes for reliability, security, and concurrency.

**pr_webhook.py:**
- Fixed resource leak in `__aexit__` - cleanup errors now isolated to prevent masking exceptions
- Added semaphore protection to `_review_file_group()` and `_cross_file_analysis()` for AI API rate limiting
- Added input validation in `_fetch_changed_files()` for malformed API responses
- Added 30s timeout to table storage operations in `_save_review_history()`
- Moved `os` and `pathlib` imports to module level

**reliability_health.py:**
- Fixed health score logic bug - scores 80-89 now correctly return "healthy" not "degraded"
- Sanitized all error responses - removed internal exception details from API responses
- Added bool check in days validation (bool is subclass of int in Python)
- Added consistent error response structure with `error_code` instead of `error_type`
- Moved `re` import to module level
- Added `Optional` type hint for repository parameter

## [2.7.2] - 2025-12-10

### Fixed - Reliability and Security Hardening

Comprehensive code review of all `src/services/` files with fixes for reliability, security, and DoS protection.

**diff_parser.py:**
- Added path traversal protection via `_validate_file_path()` helper
- Added DoS protection with MAX_DIFF_LINES (100,000) limit
- Fixed line calculation in `format_section_for_review`
- Added try/except error handling in fallback parser

**feedback_tracker.py:**
- Added pr_id type coercion with bounds checking (0 < pr_id < 2147483647)
- Added thread_id type validation from API responses
- Added JSON size validation (MAX_JSON_FIELD_SIZE) before parsing
- Sanitized author field for control characters

**file_type_registry.py:**
- Added MAX_EXTENSION_LENGTH (50 chars) validation
- Made `_build_extension_map()` thread-safe with atomic assignment

**idempotency_checker.py:**
- Added `_validate_string_param()` for injection/DoS prevention
- Validated all string inputs (repository, project, event_type, source_commit_id)
- Added result_summary truncation to 1000 chars

**pattern_detector.py:**
- Added MAX_PATTERN_REVIEWS (10,000) limit to prevent unbounded queries
- Validated days parameter (1-365) and repository parameter
- Added type validation before JSON.loads for issue_types and files
- Validated JSON.loads result is actually a list before iteration

**response_cache.py:**
- Added JSON size validation before deserializing cached review results
- Added type checking for review_json field
- Added try-except for JSON parsing and ReviewResult construction
- Added timeout (5s) on cache hit metadata update operations

**New Constants (src/utils/constants.py):**
- `MAX_DIFF_LINES = 100_000` - DoS protection for diff parsing
- `MAX_JSON_FIELD_SIZE = 10_000` - JSON field size limit for parsing

## [2.7.1] - 2025-12-08

### Fixed - Bug Fixes for Few-Shot Learning

This release addresses 19 issues found during code review of the v2.7.0 feature:

**Critical Fixes:**
- Fixed potential division by zero in learning context statistics calculation
- Added OData datetime format validation before query interpolation

**High Priority Fixes:**
- Added type coercion for file_path to handle non-string values from Table Storage
- Added prompt size limits (MAX_LEARNING_SECTION_LENGTH = 10000) to prevent prompt bloat
- Fixed null check in sample context slicing for rejection patterns

**Medium Priority Fixes:**
- Fixed off-by-one error in max examples limit using MAX_TOTAL_EXAMPLES_IN_PROMPT
- Added consistent severity handling with lowercase normalization
- Improved datetime fallback to use 30-day-ago default instead of datetime.min
- Added days parameter validation with type check and clamping (1-365)
- Added KeyError protection using .get() in statistics loop
- Added deduplication of examples by (pr_id, thread_id) to prevent duplicates
- Added backtick escaping for severity field in few-shot examples
- Added empty rejection patterns check with early return
- Added repository parameter validation with type and empty string checks
- Replaced magic number 5 with FEEDBACK_MIN_SAMPLES constant in factory.py

**Low Priority Fixes:**
- Improved logging of rejection pattern analysis with total counts
- Added acceptance_count upper bound (le=10000) in FeedbackExample model
- Added TODO comment for placeholder text in example extraction

**New Constant:**
- `MAX_LEARNING_SECTION_LENGTH = 10000` - Maximum characters for learning section

## [2.7.0] - 2025-12-08

### Added - Few-Shot Learning from Feedback

**Major Feature: AI learns from team feedback to improve review quality**

This release implements a lightweight feedback learning loop that adapts AI reviews based on team behavior - no model retraining required. The system uses prompt-based reinforcement with few-shot examples.

**Architecture:**
```
Feedback Data → Aggregate Stats → Few-Shot Examples → Dynamic Prompts → Improved Reviews
```

**New Models (src/models/feedback.py):**

1. **FeedbackExample** - Stores accepted suggestions for few-shot learning
   - `issue_type`: Type of issue that was flagged
   - `code_snippet`: Code that was flagged (truncated, sanitized)
   - `suggestion`: AI suggestion that was accepted
   - `file_path`: File context for the example
   - `severity`: Issue severity level
   - `acceptance_count`: Times similar suggestions were accepted

2. **RejectionPattern** - Tracks patterns team consistently rejects
   - `issue_type`: Type of issue rejected
   - `reason`: Inferred reason for rejection
   - `rejection_count`: Number of rejections
   - `sample_context`: Sample file/path context

3. **LearningContext** - Enhanced learning context combining all data
   - Aggregate statistics (existing)
   - Few-shot examples by issue type (NEW)
   - Rejection patterns to avoid (NEW)
   - Backward compatibility via `to_legacy_dict()`

**New FeedbackTracker Methods (src/services/feedback_tracker.py):**

1. `_extract_accepted_examples()` - Extracts few-shot examples from positive feedback
   - Groups by issue type
   - Selects most recent examples
   - Limits to `MAX_EXAMPLES_PER_ISSUE_TYPE` (3) per type

2. `_analyze_rejection_patterns()` - Identifies patterns team rejects
   - Counts rejections by issue type
   - Requires `MIN_REJECTIONS_FOR_PATTERN` (3) to be significant
   - Returns top `MAX_REJECTION_PATTERNS` (5) patterns

3. `get_enhanced_learning_context()` - Returns full LearningContext
   - Combines statistics, examples, and patterns
   - Time-windowed analysis (configurable days)
   - Returns LearningContext model

**New PromptFactory Methods (src/prompts/factory.py):**

1. `_build_few_shot_examples_section()` - Formats examples for prompt injection
   - Sanitizes all user-controlled content
   - Limits total examples to `MAX_TOTAL_EXAMPLES_IN_PROMPT` (10)

2. `_build_rejection_patterns_section()` - Formats rejection patterns
   - Warns AI to avoid flagging these patterns
   - Unless critical severity with clear security implications

3. `build_enhanced_learning_section()` - Combines all learning sections
   - Handles both LearningContext model and legacy dict
   - Graceful fallback for insufficient data

**New Constants (src/utils/constants.py):**

```python
# Feedback Learning Settings (v2.7.0)
MAX_EXAMPLES_PER_ISSUE_TYPE = 3       # Examples per issue type
MAX_TOTAL_EXAMPLES_IN_PROMPT = 10     # Total examples in prompt
MAX_EXAMPLE_CODE_SNIPPET_LENGTH = 500 # Code snippet max chars
MAX_EXAMPLE_SUGGESTION_LENGTH = 300   # Suggestion max chars
LEARNING_CONTEXT_DAYS = 90            # Days to analyze
MIN_EXAMPLE_QUALITY_RATE = 0.8        # Min acceptance rate
MAX_REJECTION_PATTERNS = 5            # Patterns to include
MIN_REJECTIONS_FOR_PATTERN = 3        # Min rejections needed
```

**Files Changed:**
- `src/models/feedback.py` - Added FeedbackExample, RejectionPattern, LearningContext
- `src/services/feedback_tracker.py` - Added extraction and analysis methods
- `src/prompts/factory.py` - Added prompt injection methods
- `src/utils/constants.py` - Added feedback learning constants
- `src/utils/config.py` - Version bump to 2.7.0

**Why This Approach:**
- Lightweight: No model fine-tuning or retraining
- Fast: Examples extracted from existing feedback data
- Adaptive: Improves with each accepted/rejected suggestion
- Reversible: Just modify prompts, no model changes
- Based on 2025 best practices from GitHub Copilot, SonarQube patterns

### Fixed - Bug Fixes from Code Review

**Issues identified and fixed during code review of v2.7.0 feature:**

1. **Severity "unknown" Fails Pydantic Validation** (CRITICAL)
   - FeedbackEntity model requires severity to be: critical, high, medium, low, info
   - Changed default from "unknown" to "medium"
   - Added parsing to extract severity from comment text
   - File: `src/services/feedback_tracker.py`

2. **Negative Filter Logic Inverted** (HIGH)
   - `not e.get("is_positive", True)` incorrectly treated missing fields as negative
   - Changed to explicit `e.get("is_positive") is False` for accurate filtering
   - File: `src/services/feedback_tracker.py`

3. **Missing Entry Validation** (HIGH)
   - Added `isinstance(e, dict)` checks before dictionary access
   - Prevents TypeError when processing malformed feedback entries
   - File: `src/services/feedback_tracker.py`

4. **Timezone-Naive Datetime Comparison** (HIGH)
   - String comparison for datetime sorting was fragile
   - Added proper datetime parsing helper with timezone handling
   - Handles ISO format strings with proper UTC fallback
   - File: `src/services/feedback_tracker.py`

5. **Backtick Escaping in Prompt Injection** (HIGH)
   - Backticks in user content could break markdown code block formatting
   - Added escaping: `replace("`", "'")`
   - Applies to file_path, code_snippet, and suggestion fields
   - File: `src/prompts/factory.py`

6. **Per-Entry Error Handling** (MEDIUM)
   - Added try-except around individual entry processing in `get_enhanced_learning_context()`
   - One bad entry no longer fails entire context generation
   - Logs warning and continues processing
   - File: `src/services/feedback_tracker.py`

7. **Missing Validators on RejectionPattern** (MEDIUM)
   - Added `sanitize_content` validator for null byte and injection protection
   - Matches existing sanitization in FeedbackExample model
   - File: `src/models/feedback.py`

8. **Magic Number Instead of Constant** (MEDIUM)
   - Changed hardcoded `5` to `FEEDBACK_MIN_SAMPLES` constant
   - In `LearningContext.has_sufficient_data()` method
   - File: `src/models/feedback.py`

**Files Changed:**
- `src/services/feedback_tracker.py` - Entry validation, datetime parsing, error handling
- `src/prompts/factory.py` - Backtick escaping for prompt security
- `src/models/feedback.py` - RejectionPattern validators, constant usage

---

## [2.6.37] - 2025-12-08

### Fixed - Third Round Bug Fixes from Code Review

**Changes:**

1. **Path Validation Order in Response Cache** (MEDIUM)
   - Fixed path validation to strip Azure DevOps leading slashes BEFORE absolute path checks
   - Previously, paths like `/main.tf` were incorrectly rejected at early check stage
   - Unified path processing flow for consistent behavior

2. **Per-Thread Error Handling in Feedback Tracker** (MEDIUM)
   - Added try/catch around individual thread processing in `_collect_pr_feedback`
   - A single malformed thread no longer causes entire PR feedback collection to fail
   - Logs warning and continues processing remaining threads

3. **Properties Type Validation in Feedback Tracker** (MEDIUM)
   - Added validation that `properties` dict is actually a dict before use
   - Added try/catch around reaction count int conversion
   - Protects against malformed Azure DevOps API responses

4. **Overflow Check Order in Token Aggregation** (MEDIUM)
   - Changed check from AFTER to BEFORE addition in `aggregate_results`
   - Prevents value from temporarily exceeding MAX_AGGREGATED_TOKENS/MAX_AGGREGATED_COST
   - Improved logging to show both current value and value being added

5. **File Type Registry Version Sync** (LOW)
   - Updated stale version docstring from 2.6.1 to 2.6.37
   - Registry file was functional but had outdated version marker

**Files Changed:**
- `src/services/response_cache.py` - Path validation order fix
- `src/services/feedback_tracker.py` - Per-thread error handling + properties validation
- `src/models/review_result.py` - Overflow check order fix
- `src/services/file_type_registry.py` - Version sync
- `src/utils/config.py` - Version bump to 2.6.37

**Dependency Verification:**
All dependencies verified current for 2025 via web search:
- Azure SDKs (azure-functions, azure-identity, azure-keyvault-secrets, azure-data-tables)
- OpenAI SDK patterns (AsyncAzureOpenAI)
- Python async patterns (asyncio.to_thread)
- Pydantic v2, tenacity, structlog, tiktoken
- Azure DevOps REST API v7.1 (still current, v7.2 is preview only)

---

## [2.6.36] - 2025-12-08

### Fixed - Second Round Bug Fixes from Code Review

**Changes:**

1. **DateTime Format Consistency in Feedback Tracker** (MEDIUM)
   - Aligned OData datetime format in `feedback_tracker.py` with `pattern_detector.py`
   - Changed to use `datetime'{iso_format}'` format for consistency

2. **Days Parameter Validation in Pattern Detector** (MEDIUM)
   - Added validation for `days` parameter (1-365 range)
   - Prevents DoS via excessive date range queries

3. **Session Reinitialization Logic in Azure DevOps Client** (LOW)
   - Simplified session handling - removed redundant `close()` on already-closed session
   - Session reference is now cleared when closed, avoiding double-close errors

4. **Response Cache Path Validation** (MEDIUM)
   - Fixed path validation to strip leading slashes before absolute path check
   - Consistent with `pr_webhook.py` path handling for Azure DevOps root-relative paths

5. **CircuitBreakerManager Lock Initialization** (HIGH)
   - Changed class-level `asyncio.Lock()` to lazy initialization via `_get_lock()` method
   - Prevents event loop binding issues when module is imported before loop starts

6. **AI Client Close Timeout Protection** (LOW)
   - Added 5-second timeout to `close()` method to prevent hung shutdown
   - Gracefully handles timeout and errors with proper logging

**Files Changed:**
- `src/services/feedback_tracker.py` - DateTime format fix
- `src/services/pattern_detector.py` - Days validation
- `src/services/azure_devops.py` - Session logic simplification
- `src/services/response_cache.py` - Path validation fix
- `src/services/circuit_breaker.py` - Lazy lock initialization
- `src/services/ai_client.py` - Close timeout protection
- `src/utils/config.py` - Version bump to 2.6.36

---

## [2.6.35] - 2025-12-08

### Fixed - Azure DevOps API Corrections per Official v7.1 Documentation

**Root Cause:** Web search verification against official Microsoft documentation revealed API parameter issues.

**Changes:**

1. **Diffs API - Removed Invalid Parameter**
   - Removed `diffContentType=unified` - this parameter does NOT exist in the API
   - Was being silently ignored by Azure DevOps

2. **Diffs API - Added Version Type Parameters**
   - Added `baseVersionType` and `targetVersionType` parameters
   - Auto-detects whether version is a branch name or commit SHA
   - Provides explicit version interpretation to API

3. **Items API - Corrected Parameter Names**
   - Changed `versionType` → `versionDescriptor.versionType`
   - Changed `version` → `versionDescriptor.version`
   - Now matches official API documentation format

**API Verification Status:**
| Endpoint | Status |
|----------|--------|
| Get Pull Request | ✅ Correct |
| Get PR Iterations | ✅ Correct |
| Get Iteration Changes | ✅ Correct |
| Get Diffs | ✅ Fixed |
| Get Items | ✅ Fixed |
| Create Thread | ✅ Correct |
| Get Threads | ✅ Correct |

**Files Changed:**
- `src/services/azure_devops.py` - API parameter corrections
- `src/utils/config.py` - Version bump to 2.6.35

**Reference:** https://learn.microsoft.com/rest/api/azure/devops/git/

---

## [2.6.34] - 2025-12-08

### Fixed - Bug Fixes from Code Review

**Changes:**

1. **Fixed Path Validation Logic Error** (HIGH)
   - `_is_safe_path()` incorrectly rejected valid Azure DevOps root-relative paths
   - `os.path.normpath()` preserves leading `/`, causing check at line 445-447 to fail
   - Fixed by stripping leading slashes before absolute path check

2. **Added Defensive Logging for Cache Statistics**
   - Added warning log when `total_hits < total_entries` indicates data inconsistency
   - Helps identify database sync issues without crashing

3. **Added File-Level Error Handling in Diff Parser**
   - Individual file extraction failures no longer stop entire diff parsing
   - Logs warning and continues processing other files
   - Improves resilience for malformed diffs

4. **Fixed Attribute Access in Review Aggregation**
   - Used `getattr()` with defaults instead of direct attribute assignment
   - Handles immutable objects (frozen dataclasses, slots) gracefully

5. **Lowered Rate Limiter Cleanup Threshold**
   - Reduced cleanup threshold from 10,000 to 1,000 clients
   - Prevents excessive memory growth in long-running instances

**Files Changed:**
- `src/handlers/pr_webhook.py` - Fixed path validation logic
- `src/services/response_cache.py` - Added cache statistics warning
- `src/services/diff_parser.py` - Added per-file error handling
- `src/models/review_result.py` - Fixed attribute access pattern
- `function_app.py` - Lowered rate limiter cleanup threshold
- `src/utils/config.py` - Version bump to 2.6.34

---

## [2.6.33] - 2025-12-08

### Fixed - Code Review Bug Fixes and Documentation Updates

**Changes:**

1. **URL Encoding for Branch Names and File Paths**
   - Added URL encoding for `baseVersion` and `targetVersion` query parameters in `get_file_diff()`
   - Added URL encoding for `path` and `version` query parameters in `_get_file_content()`
   - Handles branches with special characters (spaces, #, ?, &)

2. **Input Validation for Statistics API**
   - Added bounds checking for `days` parameter in idempotency statistics endpoint
   - Returns 400 error for invalid values instead of 500
   - Added constants: `IDEMPOTENCY_STATS_MIN_DAYS`, `IDEMPOTENCY_STATS_MAX_DAYS`, `IDEMPOTENCY_STATS_DEFAULT_DAYS`

3. **Documentation Updates**
   - Updated README to reflect 90+ supported file types

**Files Changed:**
- `src/services/azure_devops.py` - URL encoding for query parameters
- `src/utils/constants.py` - Added idempotency statistics constants
- `function_app.py` - Input validation for days parameter
- `README.md` - Updated supported file types
- `CHANGELOG.md` - Removed company-identifiable info

---

## [2.6.32] - 2025-12-08

### Fixed - Complete URL Encoding for All Azure DevOps API Endpoints

**Problem:** Multiple Azure DevOps API endpoints were missing URL encoding for project names containing spaces. This affected projects like "My Project" throughout the entire PR review workflow.

**Root Cause:** Only some methods (`get_file_diff`, `_get_file_content`, `_get_pr_threads`) had been updated with URL encoding. Other critical methods were missing this fix.

**Fix:** Added `quote(project_id, safe='')` URL encoding to all remaining methods:
- `get_pull_request_details()` - Fetches PR metadata
- `get_pull_request_files()` - Fetches list of changed files (2 URLs)
- `post_pr_comment()` - Posts summary comment to PR
- `post_inline_comment()` - Posts inline code comments

**Files Changed:**
- `src/services/azure_devops.py` - Added URL encoding to 4 additional methods
- `src/utils/config.py` - Version 2.6.32

**Complete URL Encoding Coverage:**
| Method | Status |
|--------|--------|
| `get_pull_request_details` | ✅ v2.6.32 |
| `get_pull_request_files` | ✅ v2.6.32 |
| `get_file_diff` | ✅ v2.6.29 |
| `_get_file_content` | ✅ v2.6.29 |
| `post_pr_comment` | ✅ v2.6.32 |
| `post_inline_comment` | ✅ v2.6.32 |
| `_get_pr_threads` | ✅ v2.6.31 |

---

## [2.6.31] - 2025-12-08

### Fixed - Feedback Collection Thread Fetch URL Encoding

**Problem:** The hourly feedback collector was failing to fetch PR threads for projects with spaces in their name (e.g., "My Project"). The `_get_pr_threads` API call was silently failing, resulting in `feedback_entries: 0`.

**Root Cause:** The `_get_pr_threads` method in `azure_devops.py` was not URL-encoding the project name before using it in the API URL. Projects with spaces (like "My Project") caused 400 Bad Request errors or returned empty results.

**Fix:** Added URL encoding to `_get_pr_threads`:
```python
# v2.6.31: URL-encode project name for spaces (e.g., "My Project" -> "My%20Project")
encoded_project = quote(project_id, safe='')

url = (
    f"{self.base_url}/{encoded_project}/_apis/git/repositories/"
    f"{repository_id}/pullRequests/{pr_id}/threads"
    f"?api-version={self.api_version}"
)
```

**Files Changed:**
- `src/services/azure_devops.py` - Added URL encoding in `_get_pr_threads()` (line 1084-1085)
- `src/utils/config.py` - Version 2.6.31

**Note:** This is the same URL encoding fix applied in v2.6.29 for `_get_file_content()`, but for the threads API endpoint used by feedback collection.

---

## [2.6.30] - 2025-12-08

### Fixed - Feedback Collection DateTime Query Syntax

**Problem:** The hourly feedback collector found reviews (`reviews_checked: 1`) but collected no feedback (`feedback_entries: 0`). The `reviewed_at` query was returning 0 results despite valid review history entries.

**Root Cause:** DateTime fields (`reviewed_at`, `feedback_received_at`) are stored as ISO 8601 strings in Azure Table Storage, not native datetime types. The OData query was using datetime syntax `datetime'2025-12-08T...'` which doesn't work for string comparison.

**Fix:** Changed query syntax to use string comparison (ISO format is lexicographically sortable):
```python
# Before (wrong - datetime OData syntax for string field):
query_filter = f"reviewed_at ge datetime'{cutoff_time.isoformat()}'"

# After (correct - string comparison):
query_filter = f"reviewed_at ge '{cutoff_time.isoformat()}'"
```

**Files Changed:**
- `src/services/feedback_tracker.py` - Fixed `reviewed_at` query (line 111) and `feedback_received_at` query (line 509)
- `src/utils/config.py` - Version 2.6.30

---

## [2.6.29] - 2025-12-08

### Fixed - Diff API Project Name and URL Encoding

**Problem:** PR reviews were failing with `400 Bad Request` error when fetching file diffs. The error occurred for projects with spaces in their name (e.g., "My Project").

**Root Causes:**
1. `get_file_diff()` was passing `project_id` (UUID) but the Azure DevOps diffs API requires the project NAME
2. `_get_file_content()` wasn't URL-encoding the project name, causing 400 errors for names with spaces

**Fix 1:** Changed `pr_webhook.py` to pass project name instead of UUID:
```python
# Before:
diff = await self.devops_client.get_file_diff(
    project_id=pr_event.project_id,  # UUID - wrong!
    ...
)

# After:
diff = await self.devops_client.get_file_diff(
    project_id=pr_event.project_name,  # Name - correct!
    ...
)
```

**Fix 2:** Added URL encoding in `azure_devops.py`:
```python
from urllib.parse import quote

# URL-encode project name for spaces (e.g., "My Project" -> "My%20Project")
encoded_project = quote(project_id, safe='')
url = f"{self.base_url}/{encoded_project}/_apis/git/repositories/..."
```

**Files Changed:**
- `src/handlers/pr_webhook.py` - Pass `project_name` instead of `project_id` (line 310)
- `src/services/azure_devops.py` - Added URL encoding with `quote()` in `_get_file_content()`
- `src/utils/config.py` - Version 2.6.29

**Symptoms Before Fix:**
```
diff_fetch_failed: 400, message='Bad Request'
idempotency status: FAILED: ClientResponseError: 400, message='Bad Request'
```

**After Fix:**
```
pr_review_completed: files_reviewed=4, issues_found=6
devops_comment_posted: thread_id=117646
```

---

## [2.6.28] - 2025-12-08

### Fixed - Feedback Collection Missing repository_id

**Problem:** The hourly `feedback_collector_trigger` was not collecting feedback from resolved PR threads. The feedback table remained empty despite PRs being reviewed.

**Root Cause:** `ReviewHistoryEntity` stored the repository name but not the UUID. The `FeedbackTracker` requires the repository UUID to call Azure DevOps API for fetching thread status (resolved/won't fix).

**Fix:** Added `repository_id` field to review history:
- `src/models/feedback.py` - Added `repository_id` field to `ReviewHistoryEntity`
- `src/models/feedback.py` - Updated `from_review_result()` to accept `repository_id` parameter
- `src/handlers/pr_webhook.py` - Now passes `pr_event.repository_id` when saving review history

**Impact:** New PR reviews will store the repository UUID, enabling the feedback collector to query Azure DevOps for thread status and learn from developer feedback.

---

## [2.6.27] - 2025-12-05

### Fixed - AI Timeout for GPT-5 Large Prompts

**Problem:** GPT-5 reviews with 14K+ token prompts were timing out at 60 seconds, causing reviews to fail with `APITimeoutError`.

**Root Cause:** Two timeouts were in conflict:
- `AI_CLIENT_TIMEOUT = 60` - OpenAI client-level timeout
- `AI_REQUEST_TIMEOUT = 90` - asyncio.wait_for timeout

The client-level timeout fired first at 60 seconds, before GPT-5 could complete processing large prompts.

**Fix:** Increased both timeouts to 180 seconds (3 minutes):
```python
AI_CLIENT_TIMEOUT = 180   # was 60
AI_REQUEST_TIMEOUT = 180  # was 90
```

**Files Changed:**
- `src/utils/constants.py` - Increased timeout values
- `src/utils/config.py` - Version 2.6.27

**Symptoms Before Fix:**
```
openai.APITimeoutError: Request timed out.
duration=60093355657 (60s) error=1
circuit_breaker_failure: failure_count=2
```

---

## [2.6.26] - 2025-12-05

### Fixed - Fallback Diff Parser for Unidiff Compatibility

**Problem:** Generated diffs for new/modified files caused `unidiff.errors.UnidiffParseError: Hunk is longer than expected`, preventing reviews from processing.

**Root Cause:** The `unidiff` library is strict about hunk line counts in diff headers. Our generated diffs (when Azure DevOps API doesn't return diff blocks) had line count mismatches that unidiff rejected.

**Fix:** Added a lenient fallback parser that bypasses unidiff when it fails:
- New `_fallback_parse_diff()` method manually parses diff content
- Extracts file paths, added/removed lines, and context directly
- Creates `ChangedSection` objects without strict hunk validation
- Falls back automatically when unidiff raises `UnidiffParseError`

**Files Changed:**
- `src/services/diff_parser.py` - Added fallback parser method (~100 lines)
- `src/utils/config.py` - Version 2.6.26

**Log Output:**
```
unidiff_parse_failed_using_fallback: error="Hunk is longer than expected"
fallback_diff_parsed: total_sections=1, total_changed_lines=882
```

---

## [2.6.25] - 2025-12-05

### Fixed - Diff Generation for Unidiff Compatibility

**Problem:** Generated diffs were causing unidiff parsing failures.

**Attempted Fix:** Enhanced diff generation in `azure_devops.py`:
- Added CRLF to LF normalization for consistent parsing
- Added proper trailing newline handling
- Added `\ No newline at end of file` marker
- Added empty file handling

**Files Changed:**
- `src/services/azure_devops.py` - Enhanced `_generate_add_diff()` and `_generate_delete_diff()`
- `src/utils/config.py` - Version 2.6.25

**Note:** This fix was insufficient - v2.6.26 added the definitive fallback parser solution.

---

## [2.6.24] - 2025-12-05

### Fixed - File Content API Returns Raw Code

**Problem:** Azure DevOps Items API was returning JSON metadata instead of actual file content, causing AI to review metadata objects instead of code.

**Root Cause:** The API call was missing the download parameter to get raw file content.

**Fix:** Added `&download=true` parameter to Items API URL with proper Accept headers:
```python
url = f"{self.base_url}/{project_id}/_apis/git/repositories/{repo_id}/items"
url += f"?path={file_path}&versionDescriptor.version={version}"
url += "&download=true&api-version=7.1"
headers["Accept"] = "application/octet-stream"
```

**Files Changed:**
- `src/services/azure_devops.py` - Updated `_get_file_content()` method
- `src/utils/config.py` - Version 2.6.24

---

## [2.6.23] - 2025-12-05

### Fixed - GPT-5 Parameter Compatibility

**Critical: GPT-5 API Parameter Restrictions**
- GPT-5 and o1 reasoning models have strict parameter requirements
- Fixed temperature parameter causing `BadRequestError`
- Fixed max_completion_tokens truncating responses at 4000 tokens

**Fixes Applied:**

1. **Temperature Parameter Removed for Reasoning Models**
   - Error: `Unsupported value: 'temperature' does not support 0.2 with this model. Only the default (1) value is supported.`
   - Fix: Skip temperature parameter for GPT-5 and o1 models (they only support default value of 1)
   - Models affected: gpt-5, o1-*, o1_*

2. **OPENAI_MAX_TOKENS Increased to 128K**
   - Problem: AI responses were truncated at exactly 4000 tokens, causing `AI returned invalid JSON` errors
   - Root cause: Environment variable `OPENAI_MAX_TOKENS=4000` was limiting output
   - Fix: Updated to `OPENAI_MAX_TOKENS=128000` (GPT-5 max output capacity)
   - Note: Environment variable takes precedence over code defaults

**Files Changed:**
- `src/services/ai_client.py` - Skip temperature for reasoning models
- `src/utils/constants.py` - DEFAULT_MAX_TOKENS = 128000
- `docs/DEPLOYMENT-GUIDE.md` - Updated OPENAI_MAX_TOKENS examples
- Azure Function App setting: OPENAI_MAX_TOKENS=128000

**Symptoms Before Fix:**
```
BadRequestError: Unsupported value: 'temperature' does not support 0.2
ai_response_invalid_json: Expecting value: line 1 column 1 (char 0)
completion_tokens: 4000  # Truncated!
```

**After Fix:**
```
ai_review_completed: completion_tokens: 3687  # Natural completion
devops_comment_posted: thread_id: 117403  # Success!
```

---

## [2.6.22] - 2025-12-05

### Reverted - Azure AI Foundry Agent Integration

**Reverted v2.8.0 Foundry integration.** The azure-ai-agents SDK had authentication and API issues in the Azure Function environment.

**Back to Direct API Calls:**
- Using `AsyncAzureOpenAI` client directly with chat completions API
- System prompt in `ai_client.py` handles security and quality review
- Simpler, more reliable architecture

**Removed:**
- `src/services/foundry_client.py`
- `src/agents/` directory
- `azure-ai-agents` / `azure-ai-projects` dependencies

---

## [2.6.21] - 2025-12-05

### Fixed - Fetch Actual File Content When Diff Blocks Missing

**Problem:** Even after fixing the diff API URL (v2.6.20), the AI still found 0 issues because the Azure DevOps API was returning metadata but not actual diff content ('blocks' field missing).

**Root Cause:** The `diffs/commits` API returns file change metadata (changeType, path, objectId) but doesn't always include detailed line-by-line 'blocks' with actual content. The fallback code was generating placeholder text like `"+[New file - content not available]"` instead of actual file content.

**Solution (v2.6.21):** When the API doesn't return 'blocks', now fetch actual file content:
- **New files (`add`):** Fetch content from source branch, generate diff showing all lines as `+` additions
- **Deleted files (`delete`):** Fetch content from target branch, generate diff showing all lines as `-` deletions
- **Modified files (`edit`):** Fetch both versions and use Python's `difflib.unified_diff()` to generate proper diff

**New Methods Added:**
- `_generate_add_diff(file_path, content)` - Creates diff for new files
- `_generate_delete_diff(file_path, content)` - Creates diff for deleted files
- `_generate_edit_diff(file_path, old_content, new_content)` - Creates diff using difflib

**Files Changed:**
- `src/services/azure_devops.py` - Added content fetching fallback and 3 new diff generation methods
- `src/utils/config.py` - Version 2.6.21

---

## [2.6.20] - 2025-12-05

### Fixed - Diff Fetching 404 Errors (Final Fix)

**Problem:** v2.6.19 still had 404 errors. After consulting [Azure DevOps Diffs API documentation](https://learn.microsoft.com/en-us/rest/api/azure/devops/git/diffs/get), found the correct URL format.

**Root Cause:** Two issues with the API URL:
1. Branch refs like `refs/heads/main` should be plain branch names: `main`
2. Project ID IS required in the URL path

**Correct URL (v2.6.20):**
```
https://dev.azure.com/{org}/{project}/_apis/git/repositories/{repo}/diffs/commits?baseVersion=main&targetVersion=feature/xyz
```

**What was wrong:**
- v2.6.17: Used `GBmain` prefix (wrong for query params)
- v2.6.18: Used full refs `refs/heads/main` (should be `main`)
- v2.6.19: Removed project from URL (project IS required)

**Files Changed:**
- `src/services/azure_devops.py` - Fixed URL: project in path + plain branch names
- `src/utils/config.py` - Version 2.6.20

---

## [2.6.17] - 2025-12-05

### Changed - GPT-5 Recommended for Production

**Upgrade:** Switched from GPT-4o to GPT-5 as the recommended model for code reviews.

**Why GPT-5:**
- Superior code understanding with fewer false positives
- No longer flags standard patterns (module sources, default tags) as issues
- Finds real issues that GPT-4o missed (e.g., missing required Terraform blocks)
- Correct line number attribution for inline comments
- Better severity classification

**Testing Comparison (same Terraform policy file):**
| Aspect | GPT-4o | GPT-5 |
|--------|--------|-------|
| False positive | "IAMWildcardPermission" on module source | None |
| Real issues found | Missed actual problems | Found missing `policy_rule` block |
| Line numbers | Wrong line | Correct line 18 |

**Configuration:**
Set `AZURE_AI_DEPLOYMENT=gpt-5` in Azure Function App settings.

**Technical Notes:**
- GPT-5 is a reasoning model - uses internal reasoning tokens
- No `response_format: json_object` (may return empty content with reasoning models)
- No `temperature` parameter for Azure OpenAI reasoning models
- Uses `max_completion_tokens` instead of `max_tokens`
- JSON is extracted from freeform text response

**Files Changed:**
- `src/services/ai_client.py` - GPT-5 support with proper reasoning model handling
- `src/utils/config.py` - Version 2.6.17
- `docs/DEPLOYMENT-GUIDE.md` - Updated for GPT-5
- `docs/MANAGED-IDENTITY-SETUP.md` - Updated for GPT-5

---

## [2.6.16] - 2025-12-05

### Fixed - Enforce Specific Line Numbers in AI Responses

**Problem:** AI was inconsistently returning "File-level" (line_number: 0) instead of specific line numbers, preventing inline diff comments from being posted.

**Solution:** Strengthened prompts to enforce specific line numbers:
- System prompt: "ALWAYS provide specific line numbers - NEVER use 0"
- Response format: "line_number MUST be a specific line number from the diff"
- Added explanation that line numbers enable inline PR comments

**Files Changed:**
- `src/services/ai_client.py` - Stronger line number enforcement in system prompt
- `src/prompts/factory.py` - Updated response format requirements
- `src/utils/config.py` - Version updated to 2.6.16

---

## [2.6.15] - 2025-12-05

### Changed - Inline Comments for Critical AND High Severity

Extended inline diff comments to include high severity issues (previously critical only).

**Behavior:**
- Summary comment: Always posted, contains all issues
- Inline comments: For `severity in ("critical", "high")` AND `line_number > 0`
- Medium/Low/Info issues only appear in summary

**Files Changed:**
- `src/handlers/pr_webhook.py` - Extended inline to include high severity
- `src/utils/config.py` - Version updated to 2.6.15

---

## [2.6.14] - 2025-12-05

### Added - Hybrid Comment Approach (Summary + Critical Inline)

**Feature:** Best of both worlds for PR review comments
- Always posts 1 summary comment with all issues (clean overview)
- Posts inline comments directly in the diff for CRITICAL issues only
- Inline comments only for issues with specific line numbers (not "File-level")
- Critical issues are now visible right where the problem is in the code

**Behavior:**
- Summary comment: Always posted, contains all issues
- Inline comments: Only for `severity == "critical"` AND `line_number > 0`
- File-level critical issues still appear in summary but not inline

**Files Changed:**
- `src/handlers/pr_webhook.py` - Hybrid posting logic
- `src/utils/config.py` - Version updated to 2.6.14

---

## [2.6.13] - 2025-12-05

### Improved - Enhanced AI System Prompt for Better Review Quality

**Problem:** Reviews had too many false positives and vague suggestions
- "MissingTags" flagged on a tag policy file (nonsensical)
- "HardcodedValues" for standard Terraform default tags
- "File-level" line numbers instead of specific lines
- Vague suggestions like "Review and restrict permissions"

**Solution:** Added comprehensive CodeWarden system prompt with:
- Clear guidance on what to flag (real security issues only)
- Explicit false positive avoidance rules
- Severity guidelines for consistent classification
- Emphasis on specific line numbers and actionable fixes
- Rule: "Never flag the purpose of a file as an issue"

**Files Changed:**
- `src/services/ai_client.py` - Added `SYSTEM_PROMPT` constant with comprehensive guidance
- `src/utils/config.py` - Version updated to 2.6.13

---

## [2.6.12] - 2025-12-05

### Fixed - Single Comment Per PR & Duplicate Webhook Handling

**Issue 1: Multiple Comments Per PR**
- Previously posted 1 summary comment + N inline comments for critical/high issues
- This created noise with 4+ comments per review
- Now posts only a single summary comment containing all issues

**Issue 2: Duplicate Reviews from Simultaneous Webhooks**
- Both "pull request created" and "pull request updated" webhooks fire simultaneously
- Previous idempotency key included `event_type`, causing different keys for each webhook
- Now idempotency is based on `pr_id + repository + source_commit_id` only
- Duplicate webhooks are now correctly detected and ignored

**Issue 3: AI False Positives**
- AI was flagging "HardcodedValues" for standard Terraform default tag values
- Added explicit guidance to avoid false positives for common patterns
- Prompts now clarify: default tags, provider blocks, and naming are NOT issues
- Only actual secrets (API keys, passwords, tokens) should be flagged as hardcoded

**Files Changed:**
- `src/handlers/pr_webhook.py` - Removed inline comment posting (single comment only)
- `src/models/reliability.py` - Idempotency key excludes event_type
- `src/prompts/factory.py` - Added false positive guidance
- `src/utils/config.py` - Version updated to 2.6.12

---

## [2.6.11] - 2025-12-04

### Fixed - Reasoning Model (gpt-5/o1/o3) Response Handling

**Critical: AI Returns Empty Content with response_format: json_object**
- Reasoning models (gpt-5, o1, o3) use internal "reasoning tokens" for thinking
- When using `response_format: {"type": "json_object"}`, these models may return empty `message.content`
- The completion_tokens count includes reasoning tokens, but actual output is minimal/empty
- Error: `AI returned invalid JSON: Expecting value: line 1 column 1 (char 0)`

**Fix:**
- Added reasoning model detection (gpt-5, o1, o3, o1-preview, o1-mini, o3-mini patterns)
- Removed `response_format: json_object` for reasoning models (causes empty responses)
- Enhanced system prompt for reasoning models with explicit JSON structure instructions
- Added JSON extraction from freeform text (handles markdown code blocks, etc.)
- Added refusal detection for reasoning model responses
- Added empty content handling with informative error messages
- Added debug logging for response content preview

**Files Changed:**
- `src/services/ai_client.py` - Major updates for reasoning model handling
- `src/utils/config.py` - Version updated to 2.6.11

**New Methods:**
```python
def _is_reasoning_model(self, model: str) -> bool:
    """Check if the model is a reasoning model (gpt-5, o1, o3 family)."""

def _extract_json_from_text(self, text: str) -> Optional[Dict]:
    """Extract JSON from freeform text response (code blocks, braces)."""
```

**Symptoms Before Fix:**
```
ai_response_invalid_json: Expecting value: line 1 column 1 (char 0)
# Despite completion_tokens: 4000, content was empty
```

---

## [2.6.10] - 2025-12-04

### Fixed - Azure OpenAI gpt-5/o1 Model Parameter Restrictions

**Critical: Azure OpenAI API BadRequestError with temperature Parameter**
- Newer Azure OpenAI models (gpt-5, o1) don't support custom temperature values
- API returned: `Unsupported value: 'temperature' does not support 0.2 with this model. Only the default (1) value is supported.`

**Fix:**
- Removed `temperature` parameter for Azure OpenAI deployments (uses model default of 1)
- Retained `temperature` for direct OpenAI API (backward compatibility)
- Combined with v2.6.9 `max_completion_tokens` fix

**Files Changed:**
- `src/services/ai_client.py` - Conditional parameter selection for Azure vs OpenAI
- `src/utils/config.py` - Version updated to 2.6.10

**Code Change:**
```python
# Azure OpenAI newer models have different parameter requirements
if self.use_azure:
    # Use max_completion_tokens (newer models don't support max_tokens)
    request_params["max_completion_tokens"] = max_tokens
    # Note: temperature not set for Azure - newer models only support default (1)
else:
    # Direct OpenAI API - full parameter support
    request_params["max_tokens"] = max_tokens
    request_params["temperature"] = DEFAULT_TEMPERATURE
```

**Symptoms Before Fix:**
```
BadRequestError: Unsupported value: 'temperature' does not support 0.2 with this model
```

---

## [2.6.9] - 2025-12-04

### Fixed - Azure OpenAI max_completion_tokens Parameter

**Critical: Azure OpenAI API BadRequestError with gpt-5 Model**
- Newer Azure OpenAI models (gpt-5, o1, etc.) require `max_completion_tokens` instead of `max_tokens`
- API returned: `Unsupported parameter: 'max_tokens' is not supported with this model. Use 'max_completion_tokens' instead.`

**Fix:**
- Modified `ai_client.py` to use `max_completion_tokens` for Azure OpenAI deployments
- Retained `max_tokens` for direct OpenAI API (backward compatibility)

**Symptoms Before Fix:**
```
BadRequestError: Unsupported parameter: 'max_tokens' is not supported with this model
```

---

## [2.6.8] - 2025-12-04

### Fixed - Diff API URL Missing project_id

**Critical: Diff API Still Returning 404 Errors**
- v2.6.7 fixed version specs (`refs/heads/main` → `GBmain`) but diffs still returned 404
- Root cause: URL was missing `project_id` in the path
- Azure DevOps API requires: `/{org}/{project}/_apis/git/repositories/{repo}/...`
- We were using: `/{org}/_apis/git/repositories/{repo}/...` (missing project!)

**Fix:**
- Added `project_id` parameter to `get_file_diff()` method signature
- Updated URL to include project_id: `{base_url}/{project_id}/_apis/...`
- Updated `_get_file_content()` similarly for consistency
- Updated caller in `pr_webhook.py` to pass `project_id=pr_event.project_id`

**Additional Fix: Comprehensive str enum handling**
- Changed all `.value` accesses to `str()` for Pydantic str enum compatibility
- Fixed in: `pr_webhook.py`, `context_manager.py`, `prompts/factory.py`

**Files Changed:**
- `src/services/azure_devops.py` - Added project_id to diff API URLs
- `src/handlers/pr_webhook.py` - Pass project_id, use str() for enums
- `src/services/context_manager.py` - Use str() for enum logging
- `src/prompts/factory.py` - Use str() for category logging

**Symptoms Before Fix:**
```
error: 404, message='Not Found', url='https://dev.azure.com/org/_apis/git/repositories/...'
AttributeError: 'str' object has no attribute 'value'
```

**Expected After Fix:**
```
url='https://dev.azure.com/org/project/_apis/git/repositories/...'
```

---

## [2.6.7] - 2025-12-04

### Fixed - Diff API Version Specs and Enum Handling

**Critical: Diff API Returning 404 Errors**
- Azure DevOps diff API was returning 404 for all file diff requests
- Root cause: Branch refs were passed as-is (`refs/heads/main`) instead of version specs (`GBmain`)
- Azure DevOps API requires specific version spec prefixes:
  - `GB` for branches (e.g., `GBmain`, `GBfeature/xyz`)
  - `GC` for commits (e.g., `GC1234567890abcdef`)
  - `GT` for tags (e.g., `GTv1.0.0`)

**Fix:**
- Added `_convert_to_version_spec()` method in `azure_devops.py`
- Converts `refs/heads/branch-name` → `GBbranch-name`
- Converts commit SHAs → `GC<sha>`
- Updated `get_file_diff()` to use the conversion

**Secondary Fix: AttributeError with str enum**
- `FileCategory` is a `str` enum which can sometimes behave as a string
- Code was accessing `.value` which fails if already a string
- Changed to `str(file_type)` which works in both cases

**Files Changed:**
- `src/services/azure_devops.py` - Added version spec conversion
- `src/handlers/pr_webhook.py` - Fixed str enum access

**Symptoms Before Fix:**
```
diff_fetch_failed: 404, message='Not Found'
AttributeError: 'str' object has no attribute 'value'
```

**Expected After Fix:**
```
devops_get_file_diff: base_version=GBmain, target_version=GBfeature/xyz
```

---

## [2.6.6] - 2025-12-04

### Fixed - Azure DevOps File Fetching Bug

**Critical: PR Files Not Being Fetched**
- The PR webhook handler was expecting `pr_details.get('files', [])` to contain file list
- However, Azure DevOps `/pullRequests/{id}` endpoint does NOT include files in its response
- Files must be fetched separately via `/pullRequests/{id}/iterations/{id}/changes` endpoint
- Result: All PRs showed `file_count: 0` and `no_files_to_review` even when files existed

**Root Cause:**
- `get_pull_request_details()` in `azure_devops.py` correctly fetches PR metadata
- But PR details API doesn't return files - they require a separate API call
- `get_pull_request_files()` method existed but was never called in the handler

**Fix:**
- Modified `_fetch_changed_files()` in `pr_webhook.py` to call `get_pull_request_files()`
- Now fetches file list from iterations/changes API before processing diffs
- Converts Azure DevOps `changeEntries` format to expected file format

**Files Changed:**
- `src/handlers/pr_webhook.py` - Call `get_pull_request_files()` to fetch file list

**Symptoms Before Fix:**
```
pr_details_fetched: title="...", file_count=0
no_files_to_review
```

**Expected After Fix:**
```
files_fetched_from_iterations: file_count=N, pr_id=123
changed_files_classified: total_files=N
```

---

## [2.6.5] - 2025-12-03

### Changed - Consolidated Constants & Type Hints

**Type Hints Added:**
- `circuit_breaker.py`: Added `ParamSpec` and `TypeVar` for decorator type hints
- `ai_client.py`: Added return type hint for inner `make_api_call()` function
- `azure_devops.py`: Added return type hint for inner `make_api_call()` function
- `function_app.py`: Added `-> None` return type for `_cleanup_resources()`

### Changed - Consolidated Constants

All magic numbers and configuration values are now centralized in `src/utils/constants.py`.

**New Constants Added:**
- `MAX_LINES_PER_FILE` - Maximum lines per file for token estimation (100,000)
- `MAX_TOKENS_PER_FILE` - Maximum tokens per file cap (1,000,000)
- `STRATEGY_SMALL_FILE_LIMIT` - Max files for single-pass review (5)
- `STRATEGY_SMALL_TOKEN_LIMIT` - Max tokens for single-pass review (10,000)
- `STRATEGY_MEDIUM_FILE_LIMIT` - Max files for chunked review (15)
- `STRATEGY_MEDIUM_TOKEN_LIMIT` - Max tokens for chunked review (40,000)
- `TOKENS_PER_LINE_ESTIMATE` - Token estimation multiplier (6)
- `MAX_HUNK_LINES` - Maximum lines in a diff hunk (10,000)
- `MAX_LOGGED_ISSUE_ERRORS` - Max issue errors to log individually (10)
- `MAX_AGGREGATED_TOKENS` - Pydantic field limit for tokens (9,999,999)
- `MAX_AGGREGATED_COST` - Pydantic field limit for cost (9,999.99)
- `MAX_IDEMPOTENCY_ENTRIES` - Max entries in idempotency stats query (10,000)
- `MAX_PATTERN_REVIEWS` - Max reviews in pattern detection query (10,000)

### Updated Files
| File | Changes |
|------|---------|
| `src/utils/constants.py` | Added 13 new constants |
| `src/services/context_manager.py` | Use centralized strategy constants |
| `src/services/diff_parser.py` | Use `MAX_HUNK_LINES` |
| `src/models/review_result.py` | Use centralized error/limit constants |
| `src/services/idempotency_checker.py` | Use `MAX_IDEMPOTENCY_ENTRIES` |
| `src/services/pattern_detector.py` | Use `MAX_PATTERN_REVIEWS` |
| `src/services/circuit_breaker.py` | Decorator type hints with ParamSpec |
| `src/services/ai_client.py` | Inner function type hints |
| `src/services/azure_devops.py` | Inner function type hints |
| `function_app.py` | `_cleanup_resources()` return type |
| `src/utils/config.py` | Version 2.6.5 |
| `CHANGELOG.md` | This release |

---

## [2.6.4] - 2025-12-03

### Fixed - Bug Fixes

**Critical: Missing asyncio.to_thread in ResponseCache methods**
- Fixed `invalidate_cache()`, `get_cache_statistics()`, and `cleanup_expired_entries()` methods
- These methods were still using blocking Table Storage operations
- Location: `src/services/response_cache.py:442-638`

**High: Race Condition in ResponseCache Lock Initialization**
- Replaced asyncio.Lock with threading.Lock for rate limiting
- asyncio.Lock is event-loop bound and caused issues across workers
- Using threading.Lock is safe for quick list operations
- Location: `src/services/response_cache.py:52-89`

**Medium: Missing Type Validation for AI Response Issues**
- Added validation that `issues` field from AI response is a list
- Prevents TypeError when AI returns malformed JSON
- Location: `src/models/review_result.py:286-294`

**Medium: Error Handling in Azure DevOps Session Close**
- Wrapped connector verification in separate try block
- Verification errors no longer affect cleanup
- Session reference properly checked before access
- Location: `src/services/azure_devops.py:884-902`

### Updated Files
| File | Changes |
|------|---------|
| `src/services/response_cache.py` | Non-blocking ops in 3 methods, threading.Lock |
| `src/models/review_result.py` | Type validation for issues list |
| `src/services/azure_devops.py` | Improved close error handling |
| `src/utils/config.py` | Version 2.6.4 |
| `CHANGELOG.md` | This release |

### Bug Fixes Summary

| Issue Type | Count | Impact |
|------------|-------|--------|
| Blocking Async Operations | 3 methods | Event loop no longer blocked |
| Race Condition | 1 | Cross-worker lock issues fixed |
| Type Validation | 1 | Malformed AI responses handled |
| Error Handling | 1 | Cleanup more robust |

---

## [2.6.3] - 2025-12-03

### Fixed - Non-Blocking Table Operations

**Critical: Non-Blocking Operations in Response Cache**
- Wrapped all blocking Table Storage operations with `asyncio.to_thread()`
- Fixed `get_cached_review()` to not block the event loop
- Fixed `ensure_table_exists()`, `get_entity()`, `delete_entity()`, `update_entity()` calls
- Location: `src/services/response_cache.py:70-152`

**Critical: Non-Blocking Operations in Idempotency Checker**
- Wrapped all blocking Table Storage operations with `asyncio.to_thread()`
- Fixed `is_duplicate_request()`, `record_request()`, `update_result()`, `get_statistics()`
- Location: `src/services/idempotency_checker.py:43-336`

**High: Non-Blocking Operations in Feedback Tracker**
- Wrapped all blocking Table Storage operations with `asyncio.to_thread()`
- Fixed `collect_recent_feedback()`, `get_learning_context()`, `get_feedback_summary()`
- Fixed `upsert_entity()` and `query_entities_paginated()` calls
- Location: `src/services/feedback_tracker.py:77-530`

**High: Connection Close Verification in Azure DevOps Client**
- Added graceful shutdown delay for connection pool cleanup
- Added verification logging to confirm session closure
- Improved connector cleanup handling
- Location: `src/services/azure_devops.py:867-907`

### Updated Files
| File | Changes |
|------|---------|
| `src/services/response_cache.py` | Non-blocking get_cached_review |
| `src/services/idempotency_checker.py` | Non-blocking all methods |
| `src/services/feedback_tracker.py` | Non-blocking all table operations |
| `src/services/azure_devops.py` | Connection close verification |
| `src/utils/config.py` | Version 2.6.3 |
| `CHANGELOG.md` | This release |

### Reliability Enhancements Summary

| Issue Type | Count | Impact |
|------------|-------|--------|
| Blocking Async Operations | 4 files | Event loop no longer blocked by Table Storage |
| Connection Management | 1 file | Graceful session shutdown verified |

---

## [2.6.2] - 2025-12-03

### Fixed - Reliability Improvements

**Critical: Enhanced Async Resource Cleanup**
- `PRWebhookHandler.__aenter__`: Now properly cleans up both `ai_client` and `devops_client` on partial initialization failure
- Added try/except around cleanup to ensure best-effort resource release
- Location: `src/handlers/pr_webhook.py:59-81`

**Critical: Fixed Session Race Condition in Azure DevOps Client**
- All session operations now protected by asyncio.Lock
- Token refresh failures now properly handled with session reinitialization
- Location: `src/services/azure_devops.py:129-192`

**High: Non-Blocking Table Storage Operations**
- Wrapped `ensure_table_exists()` and `upsert_entity()` calls with `asyncio.to_thread()`
- Prevents blocking the event loop during table operations
- Location: `src/handlers/pr_webhook.py:713-736`

**High: Cache Write Timeout Protection**
- Added 5-second timeout to cache write operations
- Prevents hanging on slow Table Storage responses
- Location: `src/services/response_cache.py:380-395`

**High: Resilient Result Aggregation**
- Added per-result exception handling in `ReviewResult.aggregate()`
- One corrupted result no longer breaks entire aggregation
- Added attribute validation before accessing result properties
- Location: `src/models/review_result.py:402-441`

**Medium: Rate Limiter Memory Bounds**
- Added `MAX_TRACKED_CLIENTS = 10000` limit
- Periodic cleanup of stale clients every 60 seconds
- Prevents unbounded dictionary growth under high client diversity
- Location: `function_app.py:749-838`

### Updated Files
| File | Changes |
|------|---------|
| `src/handlers/pr_webhook.py` | Async cleanup, non-blocking table ops |
| `src/services/azure_devops.py` | Session race condition fix |
| `src/services/response_cache.py` | Cache write timeout, non-blocking ops |
| `src/models/review_result.py` | Resilient aggregation |
| `function_app.py` | Rate limiter memory bounds |
| `src/utils/config.py` | Version 2.6.2 |
| `CHANGELOG.md` | This release |

### Reliability Enhancements Summary

| Issue Type | Count | Impact |
|------------|-------|--------|
| Critical Race Conditions | 2 | Fixed concurrent access issues |
| Blocking Async Operations | 3 | Event loop no longer blocked |
| Missing Error Handling | 2 | Graceful degradation on failures |
| Memory Management | 1 | Prevented unbounded growth |

---

## [2.6.1] - 2025-12-03

### Changed - Focused File Categories

**Removed File Categories** (per user requirements)
- Removed: Rust, Kotlin, Scala, Bicep, Pulumi
- Removed: GitHub Actions, Jenkins, Dependabot
- Removed: Cargo (Rust package management)

**Added .NET Support**
- Added VB.NET support (`.vb`, `.vbs` files) with best practices
- Enhanced NuGet/project file support (`.csproj`, `.vbproj`, `.fsproj`, `.sln`, `.props`, `.targets`)
- Added support for `nuget.config`, `packages.config`, `Directory.Build.props/targets`

### Fixed - Security & Reliability (from code review)

**Critical: Race Condition in FileTypeRegistry Initialization**
- Added `threading.Lock` for thread-safe initialization
- Implemented double-check locking pattern to prevent race conditions
- Location: `src/services/file_type_registry.py:295-336`

**Critical: ReDoS Vulnerability in Path Pattern Matching**
- Added `MAX_PATH_LENGTH = 2000` limit to prevent regex denial of service
- Added null byte detection in file paths
- Added try/except around regex matching with error logging
- Location: `src/services/file_type_registry.py:2587-2651`

**High: Integer Overflow in Token Estimation**
- Added `MAX_LINES_PER_FILE = 100,000` limit
- Added `MAX_TOKENS_PER_FILE = 1,000,000` cap
- Added warning logging for excessive line counts
- Location: `src/services/context_manager.py:87-136`

### Updated Files
| File | Changes |
|------|---------|
| `src/services/file_type_registry.py` | Removed categories, added VB.NET, thread safety, ReDoS protection |
| `src/services/context_manager.py` | Added bounds checking for token estimation |
| `src/utils/config.py` | Version 2.6.1 |
| `CHANGELOG.md` | This release |

---

## [2.6.0] - 2025-12-03

### Added - Universal Code Review with Best Practices

**Major Feature: Any File Type Review**
- CodeWarden now reviews **ANY file type** with context-aware best practices
- Previously limited to 4 file types (Terraform, Ansible, Pipeline, JSON)
- Now supports **40+ file categories** with comprehensive review guidance

**New File Type Registry** (`src/services/file_type_registry.py`)
- Comprehensive `FileCategory` enum with 40+ categories:
  - **Programming Languages**: Python, JavaScript, TypeScript, Java, C#, Go, Rust, C++, Ruby, PHP, Swift, Kotlin, Scala
  - **Infrastructure as Code**: Terraform, Ansible, CloudFormation, Kubernetes, Docker, Helm, Bicep, Pulumi
  - **CI/CD Pipelines**: Azure Pipelines, GitHub Actions, GitLab CI, Jenkins
  - **Configuration**: JSON, YAML, TOML, XML, INI, ENV, Properties
  - **Web Development**: HTML, CSS, SCSS, Vue, Svelte
  - **Data & Query**: SQL, GraphQL
  - **Shell & Scripts**: Bash, PowerShell, Batch
  - **Documentation**: Markdown, RST
  - **Build Systems**: Makefile, CMake, Gradle, Maven
  - **Package Management**: NPM (package.json), Requirements (requirements.txt), Gemfile, Cargo
  - **Generic**: Fallback for unknown types (still reviewed!)

**BestPractices System**
- `BestPractices` dataclass with category-specific guidance:
  - `focus_areas`: Primary review focus points
  - `security_checks`: Security vulnerabilities to detect
  - `common_issues`: Frequent problems and anti-patterns
  - `style_guidelines`: Code style and convention checks
  - `performance_tips`: Performance optimization suggestions
- Comprehensive best practices for all 40+ categories
- Examples:
  - **Python**: SQL injection, pickle vulnerabilities, mutable default args, generators
  - **Kubernetes**: Running as root, missing network policies, resource limits, RBAC
  - **Docker**: Root user, secrets in build args, multi-stage builds, .dockerignore
  - **GitHub Actions**: Secrets in logs, action pinning with SHA, workflow permissions

**Intelligent File Classification**
- Extension-based classification (`.py` → Python, `.tf` → Terraform)
- Path pattern matching for context-aware detection:
  - `**/k8s/**/*.yaml` → Kubernetes (not generic YAML)
  - `**/.github/workflows/*.yml` → GitHub Actions
  - `**/kubernetes/**/*.yaml` → Kubernetes
  - `**/ansible/**/*.yml` → Ansible
  - `**/helm/**/*.yaml` → Helm
- Priority-based classification (path patterns > extensions)
- LRU caching for classification performance

**Dynamic Prompt Generation**
- AI prompts now include category-specific best practices
- `FileTypeRegistry.format_best_practices_for_prompt()` generates focused instructions
- Configurable max practices per prompt (`MAX_BEST_PRACTICES_IN_PROMPT = 20`)
- Security checks, common issues, and performance tips included per category

### Changed

**File Classification Behavior**
- **UNKNOWN files are now reviewed!** - Previously filtered out, now get GENERIC review
- All files in PR now receive intelligent review with appropriate best practices
- `_classify_file()` method uses registry instead of hardcoded switch

**Updated Files**:
| File | Changes |
|------|---------|
| `src/services/file_type_registry.py` | **NEW** - Core registry implementation (~2000 lines) |
| `src/models/pr_event.py` | FileCategory import, FileType alias for compatibility |
| `src/handlers/pr_webhook.py` | Registry-based classification, no UNKNOWN filtering |
| `src/prompts/factory.py` | Dynamic best practices from registry |
| `src/services/context_manager.py` | Registry-based token estimates |
| `src/utils/constants.py` | New registry constants |
| `src/utils/config.py` | Version 2.6.0 |

**New Constants** (`src/utils/constants.py`):
- `DEFAULT_TOKEN_ESTIMATE = 350` - Base token estimate for unknown types
- `MAX_BEST_PRACTICES_IN_PROMPT = 20` - Limit practices per prompt
- `FILE_CATEGORY_CACHE_SIZE = 1000` - LRU cache for classification
- `MAX_SECURITY_CHECKS_PER_CATEGORY = 5` - Limit security checks
- `MAX_COMMON_ISSUES_PER_CATEGORY = 5` - Limit common issues
- `MAX_PERFORMANCE_TIPS_PER_CATEGORY = 3` - Limit performance tips

### Technical Details

**FileTypeRegistry API**:
- `classify(file_path: str) -> FileCategory` - Classify a file
- `get_best_practices(category: FileCategory) -> BestPractices` - Get review guidance
- `get_token_estimate(category: FileCategory) -> int` - Get token estimate
- `format_best_practices_for_prompt(categories, max_practices) -> str` - Generate prompt section

**Backward Compatibility**:
- `FileType = FileCategory` alias maintained for existing code
- Old `FileType.TERRAFORM`, `FileType.ANSIBLE`, etc. still work
- `FileType.UNKNOWN` maps to `FileCategory.GENERIC`
- `FileChange.file_category` property added as alias for `file_type`

### Migration Notes

- No breaking changes - fully backward compatible with v2.5.14
- All existing code using `FileType` continues to work
- New categories automatically applied to all PRs
- Best practices immediately available for all file types

### Impact

- **Coverage**: From 4 file types to 40+ categories
- **Review Quality**: Category-specific security, issues, and performance guidance
- **Developer Experience**: All files get intelligent review, not just IaC
- **Extensibility**: Easy to add new categories via registry

---

## [2.5.14] - 2025-12-03

### Fixed - Security & Reliability Issues from Code Review

- **Critical: Race Condition in Response Cache Lock Initialization** (`response_cache.py`)
  - Fixed race condition where multiple coroutines could simultaneously create locks
  - Changed `_lock_init_lock` from lazy-initialized `asyncio.Lock` to pre-initialized `threading.Lock`
  - Thread-safe initialization now guaranteed for class-level async lock

- **Critical: Unvalidated Repository ID in Feedback Tracker** (`feedback_tracker.py`)
  - Added explicit `repository_id` field check with fallback to `PartitionKey`
  - Added UUID format validation using regex pattern
  - Returns 0 with warning log when repository_id is missing or invalid
  - Prevents API calls with malformed repository identifiers

- **High: Missing Input Validation on days Parameter** (`feedback_tracker.py`)
  - Added validation in `get_feedback_summary()` requiring integer between 1-365
  - Returns standardized error response for invalid values
  - Prevents DoS via excessive date range queries

- **High: Unprotected Exception Logging in AI Response Parsing** (`review_result.py`)
  - Added `MAX_LOGGED_ERRORS = 10` limit on individual error logs
  - Logs summary after limit reached to prevent log flooding
  - Prevents DoS attacks via malicious AI responses with many invalid issues

- **High: Missing Overflow Protection in Aggregation** (`review_result.py`)
  - Added `MAX_TOKENS = 9999999` and `MAX_COST = 9999.99` caps
  - Caps values at Pydantic field limits during aggregation
  - Logs warning when overflow protection activates
  - Prevents validation errors when aggregating many results

- **High: Weak Branch Reference Validation** (`pr_event.py`)
  - Added explicit check for path traversal pattern `..`
  - Added check for double slashes `//`
  - Added check for trailing slash
  - More restrictive regex requiring alphanumeric start/end
  - Prevents potential path traversal if branch names used in file operations

### Technical Details

- **Files Modified**: 6 files
  - `src/services/response_cache.py` - Race condition fix
  - `src/services/feedback_tracker.py` - Input validation
  - `src/models/review_result.py` - Overflow protection
  - `src/models/pr_event.py` - Branch validation
  - `src/models/reliability.py` - Version update
  - `src/services/azure_devops.py` - Version update
  - `src/utils/config.py` - Version update
- **Security Impact**: Fixes race conditions, input validation gaps, DoS vectors
- **Reliability Impact**: Improved error handling and overflow protection
- **Compatibility**: Fully backward compatible with v2.5.13

---

## [2.5.13] - 2025-12-02

### Changed - Additional Inline Comments

- **Reviewed Codebase for Comment Coverage**
  - Codebase already has comprehensive documentation with:
    - Module-level docstrings explaining purpose and version
    - Class-level docstrings describing features
    - Method-level docstrings with Args, Returns, Raises sections
    - Inline comments for complex logic

- **Added Targeted Inline Comments for Clarity**
  - `src/services/pattern_detector.py`: Added comments explaining health score thresholds
    - Threshold severity levels: >10 severe, >5 moderate, >2 minor
    - Critical issues have highest weight in health score
    - High severity contributes less than critical
    - Score clamping to valid range [0, 100]
  - `src/services/context_manager.py`: Added comments explaining review strategies
    - Small PRs: review everything in one AI call
    - Medium PRs: group related files and review each group
    - Large PRs: review each file individually, then cross-file analysis

### Technical Details

- **Files Modified**: 2 files with targeted comment improvements
- **Documentation Status**: Codebase already well-documented
- **Compatibility**: Fully backward compatible with v2.5.12

---

## [2.5.12] - 2025-12-02

### Changed - Comprehensive Type Hints Throughout Codebase

- **Added Type Hints to All Functions and Methods**
  - All `__init__` methods now return `-> None`
  - All `close` methods now return `-> None`
  - All `__aenter__` methods now return `-> "ClassName"`
  - All `__aexit__` methods now return `-> bool`
  - All standalone functions have explicit return types

- **Added Type Annotations to Class Attributes**
  - Instance variables now have explicit type annotations
  - Examples: `self.devops_client: Optional[AzureDevOpsClient] = None`
  - Dict types include key/value types: `Dict[str, str]`, `Dict[FileType, int]`

- **Files Updated** (17 files):
  - `src/handlers/pr_webhook.py`
  - `src/handlers/reliability_health.py`
  - `src/services/ai_client.py`
  - `src/services/azure_devops.py`
  - `src/services/context_manager.py`
  - `src/services/comment_formatter.py`
  - `src/services/response_cache.py`
  - `src/services/idempotency_checker.py`
  - `src/services/feedback_tracker.py`
  - `src/services/pattern_detector.py`
  - `src/services/diff_parser.py`
  - `src/prompts/factory.py`
  - `src/utils/config.py`
  - `src/utils/table_storage.py`
  - `src/utils/logging.py`
  - `src/utils/constants.py`

### Technical Details

- **Type Coverage**: All public functions now have complete type annotations
- **IDE Support**: Improved autocomplete and error detection
- **Documentation**: Types serve as inline documentation
- **Compatibility**: Fully backward compatible with v2.5.11

---

## [2.5.11] - 2025-12-02

### Changed - Centralized Constants Usage & Documentation

- **Enhanced Constants Documentation** (`src/utils/constants.py`)
  - Added comprehensive comments explaining purpose of every constant
  - Organized constants into logical sections with clear headers
  - Added new constants for HTTP connection pool settings:
    - `HTTP_CONNECTION_POOL_SIZE` (100) - Total connection pool limit
    - `HTTP_CONNECTION_LIMIT_PER_HOST` (30) - Per-host connection limit
    - `DNS_CACHE_TTL_SECONDS` (300) - DNS cache duration
  - Added `LOG_FIELD_MAX_LENGTH` (100) - Log field truncation limit
  - Added `HEALTH_SCORE_DEGRADED` (70) - Health score threshold

- **Centralized Constants in All Modules**
  - Updated 8 files to import and use centralized constants
  - Files updated:
    - `src/services/azure_devops.py` - Uses HTTP connection pool constants
    - `src/services/response_cache.py` - Uses RATE_LIMIT_WINDOW_SECONDS, TABLE_STORAGE_BATCH_SIZE
    - `src/services/feedback_tracker.py` - Uses TABLE_STORAGE_BATCH_SIZE
    - `src/services/idempotency_checker.py` - Uses TABLE_STORAGE_BATCH_SIZE
    - `src/services/pattern_detector.py` - Uses TABLE_STORAGE_BATCH_SIZE
    - `src/handlers/reliability_health.py` - Uses HEALTH_CHECK_* and HEALTH_SCORE_DEGRADED
    - `src/prompts/factory.py` - Uses LOG_FIELD_MAX_LENGTH

- **Eliminated Hardcoded Values**
  - Replaced `page_size=100` with `TABLE_STORAGE_BATCH_SIZE` (12 occurrences)
  - Replaced `window_start = now - 60` with `RATE_LIMIT_WINDOW_SECONDS`
  - Replaced connection pool literals with HTTP_* constants
  - Replaced health check thresholds with HEALTH_CHECK_* constants
  - Replaced log truncation `[:100]` with `[:LOG_FIELD_MAX_LENGTH]`

### Technical Details

- **Files Modified**: 9 files
- **New Constants Added**: 5
- **Hardcoded Values Eliminated**: 20+
- **Maintainability Impact**: All configuration now in single location
- **Compatibility**: Fully backward compatible with v2.5.10

---

## [2.5.10] - 2025-12-02

### Changed - Centralized Logging Throughout Codebase

- **Improved logging.py Robustness** (`src/utils/logging.py`)
  - Added idempotency protection - `setup_logging()` now safe to call multiple times
  - Added graceful degradation if ddtrace is not available (no more crashes)
  - Added `is_logging_configured()` function to check configuration state
  - Added `__all__` for explicit public API definition
  - Added exception handling for `patch_all()` failures

- **Centralized Logging in All Modules**
  - Updated 14 files to use `from src.utils.logging import get_logger`
  - Removed direct `import structlog` usage throughout codebase
  - Files updated:
    - `src/handlers/pr_webhook.py` - also fixed bound logger context usage
    - `src/handlers/reliability_health.py`
    - `src/services/context_manager.py`
    - `src/services/idempotency_checker.py`
    - `src/services/circuit_breaker.py`
    - `src/services/azure_devops.py`
    - `src/services/ai_client.py`
    - `src/services/diff_parser.py`
    - `src/services/response_cache.py`
    - `src/services/feedback_tracker.py`
    - `src/services/pattern_detector.py`
    - `src/models/review_result.py`
    - `src/utils/config.py`
    - `src/utils/table_storage.py`
    - `src/prompts/factory.py`

- **Fixed Bound Logger Context Consistency** (`pr_webhook.py`)
  - All logs in `handle_pr_event()` now use `request_logger` with bound pr_id/repository
  - Ensures all logs within a request include proper context for tracing

### Technical Details

- **Files Modified**: 15 files
- **Maintainability Impact**: Single source of truth for logging configuration
- **Reliability Impact**: Graceful degradation when ddtrace unavailable
- **Compatibility**: Fully backward compatible with v2.5.9

---

## [2.5.9] - 2025-12-02

### Fixed - Handlers Module Security & Reliability

- **Resource Leak in Context Manager** (`pr_webhook.py`)
  - Fixed resource leak when `AIClient().__aenter__()` raises exception
  - Added try/except wrapper to ensure `devops_client` cleanup on partial initialization
  - Prevents connection leaks on startup failures

- **Missing Input Validation on `days` Parameter** (`reliability_health.py`)
  - Added validation requiring integer between 1-365 for `get_idempotency_statistics()`
  - Returns standardized error response for invalid values
  - Prevents DoS via excessive date range queries

- **Missing Input Validation on `repository` Parameter** (`reliability_health.py`)
  - Added regex validation: alphanumeric, dash, underscore, dot (max 500 chars)
  - Prevents injection attacks via malicious repository names
  - Returns standardized error response for invalid values

- **Unsafe Table Operation Outside Try Block** (`pr_webhook.py`)
  - Moved `ensure_table_exists('reviewhistory')` inside try block
  - Prevents unhandled crashes on table creation failure

- **Missing File Path Length Validation** (`pr_webhook.py`)
  - Added length check (max 2000 chars) matching FileChange model constraint
  - Returns `FileType.UNKNOWN` for excessively long paths
  - Prevents DoS via malicious long file paths

- **Division by Zero Risk** (`reliability_health.py`)
  - Fixed `_assess_cache_health()` to check `active_entries > 0` before ratio calculation
  - Prevents potential division by zero when cache is empty

- **Hardcoded Version String** (`reliability_health.py`)
  - Replaced hardcoded "2.2.0" with `__version__` import from config
  - Ensures version consistency across all endpoints

- **Magic Number in Health Calculation** (`reliability_health.py`)
  - Defined `HEALTH_SCORE_DEGRADED = 70` constant
  - Replaces hardcoded value for maintainability

- **Float Precision in Logging** (`pr_webhook.py`)
  - Rounded `avg_per_file` to 2 decimal places in logging
  - Prevents excessively long float values in logs

- **Inconsistent Error Response Format** (`reliability_health.py`)
  - Standardized all error responses to include `status`, `timestamp`, `error`, `error_type`
  - Ensures consistent API error format

### Technical Details

- **Files Modified**: 2 files in src/handlers/
- **Security Impact**: Prevents injection attacks, DoS, and resource leaks
- **Reliability Impact**: Improved error handling and input validation
- **Compatibility**: Fully backward compatible with v2.5.8

---

## [2.5.8] - 2025-12-02

### Fixed - Models Module Input Validation & Security

- **Missing Field Length Limits** (`feedback.py`, `pr_event.py`, `reliability.py`, `review_result.py`)
  - Added `max_length` constraints to all string fields to prevent DoS attacks
  - Added `gt`/`lt` bounds to integer fields to prevent integer overflow
  - Examples: `PartitionKey: str = Field(..., max_length=1024)`, `pr_id: int = Field(..., gt=0, lt=2147483647)`

- **Missing Input Validation** (`feedback.py`)
  - Added `validate_severity()` validator to enforce valid severity values
  - Added proper datetime parsing with timezone validation in `from_table_entity()`
  - Added type checking for entity parameter

- **Branch Reference Injection** (`pr_event.py`)
  - Added `validate_branch_ref()` validator to prevent command injection
  - Checks for null bytes, newlines (log injection), and validates Azure DevOps format
  - Validates branch format: `refs/(heads|tags)/[\w\-\./_]+`

- **Email Validation** (`pr_event.py`)
  - Added `validate_email()` for basic email format validation
  - Normalizes to lowercase and strips whitespace

- **PR Title Validation** (`pr_event.py`)
  - Added `validate_title()` to reject empty/whitespace-only titles
  - Made `from_azure_devops_webhook()` stricter - raises ValueError for missing required fields

- **Path Traversal in FileChange** (`pr_event.py`)
  - Added `validate_file_path()` to check for null bytes and path traversal (`..`)
  - Mirrors validation from `review_result.py`

- **JSON Field Validation** (`feedback.py`)
  - Added `validate_json_field()` for `issue_types` and `files_reviewed` fields
  - Validates JSON structure and limits array size to 1000 items (DoS protection)

- **Circuit Breaker State Validation** (`reliability.py`)
  - Added `validate_state()` to enforce valid state values: CLOSED, OPEN, HALF_OPEN
  - Added `validate_partition_key()` to enforce YYYY-MM-DD date format

- **Review Result JSON Validation** (`reliability.py`)
  - Added `validate_review_json()` to ensure `review_result_json` contains valid JSON

- **Text Sanitization** (`review_result.py`)
  - Added `sanitize_text_fields()` to remove null bytes and limit consecutive newlines
  - Prevents markdown injection in Azure DevOps comments

- **Issues List Validation** (`review_result.py`)
  - Added `validate_issues_list()` to enforce `MAX_ISSUES_PER_REVIEW` limit
  - Auto-deduplicates issues based on file_path + line_number + issue_type

- **Better Error Handling in Parsing** (`review_result.py`)
  - Changed exception catch from `Exception` to specific `(ValueError, TypeError)`
  - Added logging for invalid issues count

- **Thread Safety Documentation** (`reliability.py`)
  - Added docstring clarification for `should_allow_request()` about TOCTOU race conditions

### Technical Details

- **Files Modified**: 4 files in src/models/
- **Security Impact**: Prevents DoS, injection attacks, and integer overflow
- **Validation Impact**: All Pydantic models now have comprehensive field constraints
- **Compatibility**: Fully backward compatible with v2.5.7

---

## [2.5.7] - 2025-12-02

### Changed - Centralized Constants & Logging

- **Centralized Logging Helper** (`src/utils/logging.py`)
  - Added `get_logger()` convenience function for centralized logger imports
  - Modules can now import from single source: `from src.utils.logging import get_logger`
  - Wraps `structlog.get_logger()` for consistent usage across codebase

- **Prompt Factory Input Limits to Constants** (`src/utils/constants.py`)
  - Added `PROMPT_MAX_TITLE_LENGTH = 500`
  - Added `PROMPT_MAX_PATH_LENGTH = 1000`
  - Added `PROMPT_MAX_MESSAGE_LENGTH = 5000`
  - Added `PROMPT_MAX_ISSUE_TYPE_LENGTH = 100`

- **Updated Files to Use Centralized Constants**
  - `src/prompts/factory.py`: Uses `PROMPT_MAX_*` constants from constants.py
  - `src/handlers/reliability_health.py`: Uses `HEALTH_SCORE_MAX` instead of hardcoded `100`
  - `src/utils/table_storage.py`: Uses `TABLE_STORAGE_BATCH_SIZE` for pagination
  - `src/services/pattern_detector.py`: Uses `HEALTH_SCORE_MAX` instead of hardcoded `100`

- **Updated Files to Use Centralized Logging**
  - `src/prompts/factory.py`: `from src.utils.logging import get_logger`
  - `src/handlers/reliability_health.py`: `from src.utils.logging import get_logger`
  - `src/utils/table_storage.py`: `from src.utils.logging import get_logger`
  - `src/services/pattern_detector.py`: `from src.utils.logging import get_logger`

### Technical Details

- **Files Modified**: 6 files
- **Maintainability Impact**: Centralizes magic numbers and logging for easier maintenance
- **Compatibility**: Fully backward compatible with v2.5.6

---

## [2.5.6] - 2025-12-02

### Fixed - Prompts Module Security (Prompt Injection Prevention)

- **CRITICAL: Prompt Injection Vulnerability** (`factory.py`)
  - User-controlled input (PR titles, file paths, issue messages) was directly interpolated into AI prompts
  - Created `_sanitize_user_input()` method that:
    - Truncates input to maximum safe lengths (DoS protection)
    - Removes common prompt injection patterns via regex
    - Blocks "ignore previous instructions", "system:", "assistant:" markers
    - Limits consecutive newlines to prevent section breaks
    - Logs potential attack attempts for security monitoring

- **HIGH: Unsafe Learning Context Injection** (`factory.py`)
  - Learning context data accepted without type validation
  - Created `_validate_learning_context()` method that:
    - Validates dictionary structure and field types
    - Sanitizes all string values in issue type lists
    - Limits list lengths to prevent DoS (max 10 items)
    - Validates numeric ranges (feedback rate 0-1, count >= 0)

- **MEDIUM: Missing Input Validation on Empty Lists** (`factory.py`)
  - Added validation checks at start of all prompt building methods
  - `build_single_pass_prompt()`: Raises ValueError if files list is empty
  - `build_group_prompt()` / `build_cross_file_prompt()`: Returns empty string with warning

- **LOW: DoS Protection via Input Length Limits** (`factory.py`)
  - Added class constants: MAX_TITLE_LENGTH=500, MAX_PATH_LENGTH=1000, MAX_MESSAGE_LENGTH=5000
  - Applied truncation in sanitization method

### Technical Details

- **Files Modified**: 3 files, +221/-41 lines in factory.py
- **Security Impact**: Prevents prompt injection attacks that could manipulate AI review results
- **Compatibility**: Fully backward compatible with v2.5.5

---

## [2.5.5] - 2025-12-02

### Fixed - Services Module Security & Reliability

- **Circuit Breaker Deadlock Vulnerability** (`circuit_breaker.py`)
  - Converted manual lock acquire/release to context manager pattern
  - Used `asyncio.timeout()` for lock acquisition timeout
  - Separated state checking (under lock) from function execution (outside lock)
  - Prevents complete application deadlock

- **Session Race Condition** (`azure_devops.py`)
  - Fixed TOCTOU race in `_get_session()` token refresh
  - Added proper session cleanup inside lock on failure
  - Implemented double-check pattern with explicit cleanup

- **Memory Exhaustion Bug** (`pattern_detector.py`)
  - Moved safety limit check BEFORE appending to list
  - Check happens during iteration, preventing excess data load
  - Prevents OOM crashes before protection activates

- **Path Traversal Vulnerability** (`response_cache.py`)
  - Added URL decoding before validation to prevent bypass
  - Check suspicious patterns in BOTH original and decoded paths
  - Added control character detection and path length limits
  - Expanded suspicious patterns list (/dev/, /sys/, ~/)

- **Resource Leak in AI Client** (`ai_client.py`)
  - Added try-except-finally block in `close()` method
  - Set `_client = None` after closing to prevent reuse
  - Added warning logging for close errors

- **Unsafe Close Method** (`azure_devops.py`)
  - Added lock protection for concurrent close calls
  - Added try-except-finally blocks for session and credential
  - Set references to None after cleanup

- **DoS Vulnerability in Diff Parser** (`diff_parser.py`)
  - Added MAX_HUNK_LINES = 10000 safety limit
  - Early termination with warning when limit exceeded
  - Prevents memory exhaustion from malicious diffs

- **DateTime Parsing Vulnerability** (`feedback_tracker.py`)
  - Added safe datetime parsing with proper exception handling
  - Handle both ISO format and timezone suffixes (Z → +00:00)
  - Proper fallback to current UTC time

- **Lock Initialization Race Condition** (`response_cache.py`)
  - Added double-check locking pattern with `_lock_init_lock`
  - Safe for concurrent initialization attempts

### Technical Details

- **Files Modified**: 9 files, +196/-99 lines
- **Security Impact**: Fixes path traversal, DoS, deadlock vulnerabilities
- **Reliability Impact**: Fixes race conditions, resource leaks, memory issues
- **Compatibility**: Fully backward compatible with v2.5.4

---

## [2.5.4] - 2025-12-02

### Fixed - Utils Module Bug Fixes

- **Invalid Log Level Handling** (`logging.py`)
  - Added validation for log level parameter in `setup_logging()`
  - Now supports case-insensitive log levels ("info", "INFO", "Info" all work)
  - Clear error message for invalid log levels instead of AttributeError
  - Prevents application crash on startup with invalid LOG_LEVEL config

- **Async/Sync Cleanup Mismatch** (`table_storage.py`, `function_app.py`)
  - Changed `cleanup_table_storage()` from async to sync function
  - Fixed resource leak where cleanup was scheduled but never executed
  - `atexit` handler now properly calls cleanup functions
  - Ensures `DefaultAzureCredential` connections are properly closed

### Technical Details

- **Files Modified**: 5 files
- **Impact**: Fixes potential resource leaks and startup crashes
- **Compatibility**: Fully backward compatible with v2.5.3

---

## [2.5.3] - 2025-12-02

### Changed - Constants Centralization

- **Centralized Magic Numbers** (`constants.py`)
  - All hardcoded values now defined in `src/utils/constants.py`
  - Single source of truth for configuration values
  - Added new constants: `FUNCTION_TIMEOUT_SECONDS`, `RATE_LIMIT_*`, `MAX_PROMPT_LENGTH`,
    `DEFAULT_RETRY_AFTER_SECONDS`, `CIRCUIT_BREAKER_LOCK_TIMEOUT_SECONDS`,
    `CACHE_MAX_WRITES_PER_MINUTE`, `MAX_COMMENT_LENGTH`, `HEALTH_SCORE_*`

- **Updated Files to Use Constants**
  - `function_app.py` - Timeouts, rate limits, payload size
  - `ai_client.py` - Timeouts, temperature, token costs, circuit breaker config
  - `azure_devops.py` - Timeouts, retry delays, comment length
  - `circuit_breaker.py` - Threshold and timeout defaults
  - `response_cache.py` - Cache TTL, table name, write rate limits
  - `feedback_tracker.py` - Feedback thresholds, analysis days
  - `pattern_detector.py` - Analysis days, health score thresholds
  - `reliability_health.py` - Health score thresholds
  - `config.py` - Default values derived from constants
  - `models/reliability.py` - Circuit breaker defaults

- **Aligned CACHE_TTL_DAYS** - Changed from 7 to 3 days to match actual config

### Technical Details

- **Files Modified**: 11 files, +149/-73 lines
- **Impact**: Improved maintainability, easier configuration management
- **Compatibility**: Fully backward compatible with v2.5.2

---

## [2.5.2] - 2025-12-02

### Fixed - Async Safety & Input Validation

- **Async Race Condition in Cache Rate Limiting** (`response_cache.py`)
  - Converted `_check_write_rate_limit()` to async using `asyncio.Lock`
  - Previous `threading.Lock` did not provide proper protection in async context
  - Prevents rate limiting bypass by concurrent async requests

- **Circuit Breaker Deadlock Prevention** (`circuit_breaker.py`)
  - Added critical documentation for lock release in finally block
  - Ensures lock is always released even if exception occurs
  - Prevents permanent service deadlock on circuit breaker

- **Prompt Length Validation** (`ai_client.py`)
  - Added `MAX_PROMPT_LENGTH` constant (1 million characters)
  - Validates prompt is non-empty string before API call
  - Prevents memory exhaustion from extremely large prompts
  - Clear error message with remediation suggestion

### Technical Details

- **Files Modified**: 3 files, +30/-11 lines
- **Security Impact**: Prevents DoS via oversized prompts, fixes async race condition
- **Compatibility**: Fully backward compatible with v2.5.1

---

## [2.5.1] - 2025-12-02

### Fixed - Security & Concurrency Issues

- **Race Condition in Rate Limiter** (`function_app.py`)
  - `get_remaining()` method now properly acquires async lock before accessing shared state
  - Prevents incorrect rate limit calculations under concurrent requests

- **Race Condition in Cache Write Rate Limiter** (`response_cache.py`)
  - Added `threading.Lock` to protect class-level `_write_timestamps` list
  - Prevents race conditions when multiple cache instances check/update write limits

- **Path Traversal Edge Cases** (`pr_webhook.py`, `response_cache.py`)
  - Added empty/None path validation at start of `_is_safe_path()`
  - Moved suspicious pattern checks BEFORE normalization to prevent bypass
  - Added explicit check for paths starting with ".." after normalization
  - Added type checking to ensure path is a string

- **Context Manager Protocol** (`azure_devops.py`, `ai_client.py`)
  - Added explicit `return False` in `__aexit__` methods
  - Ensures exceptions are never inadvertently suppressed

### Technical Details

- **Files Modified**: 5 files, +91/-50 lines
- **Security Impact**: Closes path traversal edge cases, fixes race conditions
- **Compatibility**: Fully backward compatible with v2.5.0

---

## [2.5.0] - 2025-12-01

### Documentation Updates

- **Azure DevOps API Version**
  - Updated from API version 7.0 to 7.1 (current recommended)
  - Updated API reference links in documentation

- **host.json Configuration**
  - Added `extensionBundle` configuration for automatic extension updates
  - Version range `[4.*, 5.0.0)` for latest extension support

- **Deployment Guide Updates**
  - Added Python 3.13 GA support note
  - Added Python 3.9 end-of-support warning (October 2025)
  - Added Flex Consumption Plan hosting option table
  - Added webhook security best practices section
  - Updated host.json troubleshooting with extensionBundle example

### Added - Reliability & Observability Improvements

- **Centralized Version Management**
  - Single source of truth: `src/utils/config.py:__version__`
  - All modules and endpoints use centralized version
  - Eliminates version inconsistencies across codebase

- **Timer Trigger Retry Logic**
  - Configurable retry with exponential backoff
  - `TIMER_MAX_RETRIES=3` and `TIMER_RETRY_DELAY_SECONDS=30`
  - Applied to both feedback collector and pattern detector triggers
  - Proper error logging with attempt counts

- **Concurrency Limiting**
  - Semaphore-based concurrency control for parallel operations
  - `MAX_CONCURRENT_REVIEWS=10` setting to prevent resource exhaustion
  - Applied to diff fetching and hierarchical reviews
  - Prevents overwhelming Azure DevOps API

- **Circuit Breaker Admin Endpoint**
  - New `/api/circuit-breaker-admin` endpoint
  - Reset all circuit breakers: `POST ?action=reset`
  - Reset specific service: `POST ?action=reset&service=openai`
  - Get status: `POST` (no action parameter)

- **PatternDetector Metrics**
  - `PatternDetectorMetrics` dataclass for observability
  - Tracks: duration, repositories analyzed, patterns found, errors
  - `last_metrics` property for accessing most recent analysis metrics
  - Detailed logging with metrics in analysis completion

- **Result Aggregation Validation**
  - Validates results before aggregation (filters None values)
  - Type checking for ReviewResult instances
  - Logs skipped invalid results with counts

### Fixed Issues

- **CACHE_TTL_DAYS in Settings**
  - Added `CACHE_TTL_DAYS` to Settings class properly
  - Response cache now uses settings value directly
  - No more fallback to `getattr()` workaround

- **Error Context in Parallel Operations**
  - `asyncio.gather()` with `return_exceptions=True` replaced
  - Custom wrapper functions preserve error context (file_path, error_type)
  - Partial failures logged with counts
  - Each failed operation tracked individually

- **Deprecated Session Property Removed**
  - Removed sync `session` property from AzureDevOpsClient
  - All callers must use `await _get_session()`
  - Eliminates error-prone synchronous access pattern

### Changed

- **Settings Class**
  - Added `CACHE_TTL_DAYS: int = 3`
  - Added `MAX_CONCURRENT_REVIEWS: int = 10`
  - Added `TIMER_MAX_RETRIES: int = 3`
  - Added `TIMER_RETRY_DELAY_SECONDS: int = 30`

- **Parallel Operations**
  - `_fetch_changed_files()` uses semaphore-limited fetching
  - `_hierarchical_review()` uses semaphore for file reviews
  - Both preserve error context with tuple returns

### Technical Details

- **Version**: `from src.utils.config import __version__` for all version references
- **Concurrency**: `asyncio.Semaphore(settings.MAX_CONCURRENT_REVIEWS)`
- **Retry**: For loop with `asyncio.sleep(retry_delay)` between attempts
- **Metrics**: `@dataclass` with `to_dict()` for structured logging

### Migration Notes

- No breaking changes - fully backward compatible with v2.4.0
- Set `MAX_CONCURRENT_REVIEWS` to tune parallel operation limits
- Set `TIMER_MAX_RETRIES` and `TIMER_RETRY_DELAY_SECONDS` for timer behavior
- Circuit breaker admin endpoint requires function key authentication

---

## [2.4.0] - 2025-12-01

### Added - Phase 2 Learning & Developer Experience

- **Phase 2 Learning Context Integration**
  - AI prompts now include team preference context from historical feedback
 -value issue types are prioritized (>70% acceptance rate)
 -value issue types are de-prioritized (<30% acceptance rate)
  - Requires minimum 5 feedback entries for statistical significance
  - Implemented in `prompts/factory.py:_build_learning_context_section()`

- **SuggestedFix Model**
  - New `SuggestedFix` Pydantic model with before/after code snippets
  - `suggested_fix` field added to `ReviewIssue` model
  - Copy-pasteable solutions for critical/high severity issues
  - Schema: `{description, before, after, explanation}`

- **Dry-Run Mode**
  - Set `DRY_RUN=true` environment variable to skip posting to Azure DevOps
  - Full review workflow executes, comments are logged but not posted
  - Useful for testing and development without affecting PRs

- **Function-Level Timeout Protection**
  - 8-minute timeout (480s) on PR review operations
  - Graceful 504 Gateway Timeout response for long-running reviews
  - Leaves buffer before Azure Functions' 10-minute hard limit

- **Webhook Handler Unit Tests**
  - Comprehensive test suite in `tests/test_pr_webhook_handler.py`
  - Tests for strategy selection, dry-run mode, result aggregation
  - Tests for file path validation and SuggestedFix model
  - Improves code coverage and regression detection

- **Storage Rate Limiting**
  - Max 100 writes per minute to Table Storage
  - Prevents quota exhaustion from runaway processes
  - Class-level tracking in `ResponseCache`

### Fixed Issues

- **Removed Unused Anthropic SDK**
  - `anthropic==0.40.0` removed from requirements.txt
  - Reduces attack surface and deployment size

- **Improved Exception Handling**
  - Replaced bare `except Exception` with specific exception types
  - Network errors return 503 Service Unavailable
  - Validation errors return 400 Bad Request
  - Context (pr_id, repository) preserved in all error logs

- **File Path Validation**
  - `ReviewIssue.file_path` now validates against path traversal
  - Rejects null bytes, `../` patterns, and suspicious system paths
  - Pydantic `field_validator` for automatic validation

### Changed

- **Response Cache TTL** - Default reduced from 7 to 3 days
  - Better alignment with 24-hour feedback collection window
  - Configurable via `CACHE_TTL_DAYS` environment variable

- **Token Metrics Exposure**
  - `tokens_used` and `estimated_cost_usd` included in webhook response
  - Structured logging includes token metrics for Datadog dashboards
  - Enables cost monitoring and optimization

- **Performance Test Marker**
  - Added `performance` marker to pytest.ini
  - Run performance tests separately: `pytest -m performance`

- **Pattern Detector**
  - Added async context manager for proper resource cleanup
  - Consistent with FeedbackTracker implementation

### Technical Details

- **Learning Context**: Requires 5+ feedback entries, 70%/30% thresholds for high/low value
- **Timeout**: `asyncio.wait_for()` with 480s timeout at function level
- **Dry-Run**: `DRY_RUN` env var, handler attribute, skips `_post_review_results()`
- **Rate Limiting**: Class-level `_write_timestamps` list, 60-second sliding window
- **File Validation**: Pydantic `field_validator`, checks traversal/null/suspicious

### Migration Notes

- No breaking changes - fully backward compatible with v2.3.0
- Set `DRY_RUN=true` to test without posting comments
- Set `CACHE_TTL_DAYS=7` to restore previous cache TTL behavior
- Run `pip install -r requirements.txt` to remove Anthropic SDK

---

## [2.3.0] - 2025-12-01

### Added - Security & Performance Improvements

- **Rate Limiting on Webhook Endpoint**
  - In-memory sliding window rate limiter (100 requests/minute per IP)
  - Proper `429 Too Many Requests` responses with `Retry-After` header
  - Client IP extraction supporting `X-Forwarded-For` for load balancer deployments
  - Prevents webhook abuse and DoS attacks

- **Suggested Fix Generation**
  - AI prompts now request code-level fix suggestions
  - New `suggested_fix` field in issue responses with `before`/`after` code snippets
  - Copy-pasteable solutions for critical and high severity issues
  - Explanation of why fixes work for developer education

- **Connection Pool Tuning**
  - Custom `TCPConnector` configuration for Azure DevOps client
  - 100 total connections, 30 per-host limit
  - DNS cache with 5-minute TTL
  - Automatic closed connection cleanup
  - Improved performance under high load

- **Resource Cleanup Handlers**
  - `atexit` handler for proper shutdown cleanup
  - `cleanup_secret_manager()` called on application shutdown
  - Prevents credential resource leaks in long-running instances

### Fixed Bug Fixes

- **Circuit Breaker Infinite Wait** (Critical)
  - Added 30-second timeout on lock acquisition
  - Prevents indefinite blocking when lock is held
  - Proper lock release with `try/finally` blocks
  - Non-blocking success/failure recording

- **Missing asyncio Import** (Critical)
  - Added `import asyncio` to ai_client.py
  - Fixes `asyncio.wait_for` usage in API timeout handling

### Changed

- **AI Client (ai_client.py)** - Version 2.3.0
  - Added missing asyncio import
  - Enhanced request timeout handling

- **Circuit Breaker (circuit_breaker.py)** - Version 2.3.0
  - Lock timeout protection (30 seconds max wait)
  - Improved lock management prevents deadlocks
  - Better error logging for timeout scenarios

- **Azure DevOps Client (azure_devops.py)** - Version 2.3.0
  - Connection pool tuning with custom TCPConnector
  - Better resource utilization for concurrent requests

- **PR Webhook Handler (pr_webhook.py)** - Version 2.3.0
  - Integrated rate limiting check at entry point
  - Improved request validation flow

- **Prompt Factory (factory.py)** - Version 2.3.0
  - Enhanced response format with suggested_fix structure
  - Explicit instructions for code-level fixes

- **Function App (function_app.py)** - Version 2.3.0
  - Rate limiting middleware
  - Shutdown cleanup handlers
  - Updated health check version

### Technical Details

- **Rate Limiting**: Sliding window counter, per-IP tracking, 60-second window
- **Circuit Breaker**: 30-second lock timeout, proper try/finally release
- **Connection Pool**: TCPConnector(limit=100, limit_per_host=30, ttl_dns_cache=300)
- **Cleanup**: atexit handler for SecretManager credential cleanup

### Migration Notes

- No breaking changes - fully backward compatible with v2.2.0
- Rate limiting activates automatically (100 req/min per IP)
- Circuit breaker improvements are transparent
- Connection pool tuning is automatic

---

## [2.2.0] - 2025-11-30

### Added - Reliability Enhancements (Production Ready)
- **Request Idempotency System**
  - `IdempotencyChecker` service prevents duplicate PR review processing
  - Uses Azure Table Storage with 48-hour TTL for request tracking
  - Generates deterministic request IDs from PR metadata
  - Handles webhook retries gracefully without wasting resources
  - Integrated into PR webhook handler at entry point
  - Methods: `is_duplicate_request()`, `record_request()`, `update_result()`, `get_statistics()`

- **Circuit Breaker Pattern**
  - `CircuitBreaker` and `CircuitBreakerManager` for resilient external service calls
  - Three states: CLOSED (normal), OPEN (failing fast), HALF_OPEN (testing recovery)
  - Configurable failure thresholds and timeout periods
  - Integrated into OpenAI API client (ai_client.py)
  - Integrated into Azure DevOps API client (azure_devops.py)
  - Prevents cascading failures and reduces latency during outages
  - Automatic recovery testing after cooldown period

- **Response Caching**
  - `ResponseCache` service caches AI review responses by content hash
  - SHA256-based content hashing for identical diff detection
  - 7-day TTL with automatic cache expiration
  - Potential cost savings: 20-30% on repeated reviews (force-push scenarios)
  - Integrated into file review workflow (_review_single_file)
  - Methods: `get_cached_review()`, `cache_review()`, `invalidate_cache()`, `cleanup_expired_entries()`, `get_cache_statistics()`

- **Reliability Health Endpoint**
  - New `/api/reliability-health` endpoint for monitoring
  - Exposes circuit breaker states, cache statistics, idempotency metrics
  - Query parameters: `feature`, `repository`, `days`
  - Provides health scores and actionable insights
  - Integrated with Datadog for alerting

- **Performance Benchmarks**
  - Comprehensive benchmark suite using pytest-benchmark
  - Measures critical paths: diff parsing, caching, token counting
  - Performance thresholds for regression detection
  - CI/CD integration for automated performance monitoring
  - Located in `tests/performance/test_benchmarks.py`

- **Enhanced Datadog Monitoring**
  - Datadog dashboard configuration for reliability metrics
  - 17 widgets covering circuit breakers, cache, idempotency, performance
  - Custom metrics: cache hit rate, duplicate requests, cost savings
  - Alert configurations for critical issues
  - Located in `monitoring/datadog-reliability-dashboard.json`

- **Data Models for Reliability**
  - `IdempotencyEntity` - Request deduplication tracking
  - `CacheEntity` - Response cache storage
  - `CircuitBreakerState` - Circuit breaker state management
  - All models in `src/models/reliability.py`

### Changed
- **AI Client (ai_client.py)** - Version 2.2.0
  - Added circuit breaker protection around OpenAI API calls
  - Fail-fast behavior when circuit is open
  - Enhanced error handling for CircuitBreakerError

- **Azure DevOps Client (azure_devops.py)** - Version 2.2.0
  - Added circuit breaker protection around API calls
  - Improved resilience for PR details, file fetching, diff retrieval

- **PR Webhook Handler (pr_webhook.py)** - Version 2.2.0
  - Added idempotency checking at request entry point
  - Integrated response caching for file reviews
  - Updates idempotency record with final result summary
  - Enhanced logging for cache hits and duplicate requests

- **Function App Health Check** - Version 2.2.0
  - Updated health endpoint version number
  - Added new reliability-health endpoint

- **Dependencies Updated**
  - Added `pytest-benchmark==4.0.0` to requirements-dev.txt for performance testing

### Technical Details
- **Idempotency**: Table Storage table `idempotency`, partitioned by date (YYYY-MM-DD)
- **Caching**: Table Storage table `responsecache`, partitioned by repository
- **Circuit Breaker**: In-memory state management with async locks
- **Performance**: Benchmarks target <1ms for cache/idempotency operations
- **Monitoring**: Custom Datadog metrics for all reliability features

### Migration Notes
- No breaking changes - fully backward compatible with v2.1.0
- Tables created automatically on first use
- Circuit breakers initialize in CLOSED state
- Cache gradually builds up with reviews
- Idempotency kicks in automatically for duplicate webhooks

### Cost Impact
- **Savings**: 20-30% reduction in AI API costs from caching (expected)
- **Additional Costs**: Minimal Table Storage costs for idempotency/cache (~$0.10/month)
- **Net Impact**: Significant cost savings with negligible overhead

## [2.1.0] - 2025-11-30

### Added - Phase 2 Features (Production Ready)
- **Feedback Tracking System** - Production implementation
  - `FeedbackTracker` class with full functionality (was stub in 2.0.0)
  - Hourly feedback collection from Azure DevOps PR threads
  - Tracks thread status changes (resolved, won't fix, reactions)
  - Learns high-value vs low-value issue types from team feedback
  - Provides learning context to AI for focused reviews
  - Methods: `collect_recent_feedback()`, `get_learning_context()`, `get_feedback_summary()`

- **Pattern Detection System** - Production implementation
  - `PatternDetector` class with full functionality (was stub in 2.0.0)
  - Identifies recurring issues appearing in >30% of PRs
  - Detects problematic files with frequent issues
  - Analyzes code quality trends over time (improving/degrading/stable)
  - Calculates repository health scores (0-100)
  - Generates actionable insights and monthly reports
  - Methods: `analyze_all_repositories()`, `get_repository_health_score()`, `get_global_summary()`

- **Data Models for Phase 2**
  - `FeedbackEntity` - Stores individual feedback entries in Table Storage
  - `ReviewHistoryEntity` - Stores complete review history for pattern analysis
  - Repository-partitioned storage for efficient queries
  - Links feedback to original reviews and PRs

- **Integration Points**
  - PR webhook handler now saves all reviews to history (`_save_review_history()`)
  - Azure DevOps client added `_get_pr_threads()` for feedback collection
  - Automatic table creation on first use
  - Non-blocking storage (doesn't fail reviews on storage errors)

### Changed
- **Timer Triggers** - Now fully functional (were placeholders)
  - `feedback_collector_trigger` - Collects feedback hourly
  - `pattern_detector_trigger` - Analyzes patterns daily at 2 AM
- **AI Review Workflow** - Now includes learning context
  - Fetches team preferences before review
  - Adapts recommendations based on historical feedback
  - Focuses on high-value issue types per repository

### Technical Details
- **Storage**: Uses Azure Table Storage with Managed Identity
- **Performance**: Efficient queries with partition keys and filters
- **Error Handling**: Graceful degradation - Phase 2 failures don't block reviews
- **Logging**: Comprehensive structured logging for troubleshooting
- **Statistics**: Requires minimum 5 feedback entries for statistical significance

### Migration Notes
- No breaking changes - fully backward compatible
- Tables created automatically on first deployment
- Existing v2.0.0 deployments work immediately
- Phase 2 features activate automatically when data available

## [2.0.0] - 2025-11-30

### Added
- **Managed Identity Support** for credential-free authentication
  - Azure DevOps authentication via Azure AD tokens (eliminates PAT dependency)
  - Table Storage authentication via Managed Identity
  - Comprehensive setup guides and documentation
- **Enhanced Security**
  - Removed webhook authentication bypass in development mode
  - Added payload size limits (1MB max)
  - Added JSON depth validation (max 10 levels)
  - Added file path sanitization to prevent traversal attacks
  - Constant-time comparison for webhook secrets (prevents timing attacks)
  - Comprehensive error handling without information leakage
- **Code Quality Improvements**
  - Added extensive inline comments to complex functions
  - Fixed type hints (any → Any)
  - Added comprehensive docstrings to all functions
  - Created constants file for magic numbers
  - Moved example code to dedicated directory
- **Test Infrastructure**
  - Created comprehensive test structure
  - Added pytest configuration
  - Added example tests for security functions
  - Added test fixtures and conftest.py
- **Documentation**
  - New: `MANAGED-IDENTITY-SETUP.md` - Complete MI setup guide
  - New: `AZURE-DEVOPS-MANAGED-IDENTITY.md` - DevOps MI specific guide
  - New: `ARCHITECTURE-SECURITY.md` - Security architecture documentation
  - Updated: All docs to reflect Managed Identity usage

### Changed
- **Dependencies Updated** (all packages to latest versions)
  - azure-functions: 1.18.0 → 1.24.0
  - azure-identity: 1.15.0 → 1.19.0
  - openai: 1.12.0 → 1.58.1
  - pydantic: 2.6.1 → 2.10.3
  - aiohttp: 3.9.3 → 3.11.9
  - All other packages updated to latest stable versions
- **Breaking**: Configuration changes
  - `AZURE_STORAGE_CONNECTION_STRING` → `AZURE_STORAGE_ACCOUNT_NAME`
  - Removed connection string requirement for Table Storage
  - Health check endpoint now requires authentication (FUNCTION level)
- **Improved**: Diff fetching logic
  - Replaced placeholder diffs with actual Azure DevOps API content
  - Added proper block processing from API response
  - Enhanced unified diff formatting with detailed comments
- **Enhanced**: AI Response Validation
  - Comprehensive schema validation
  - Validates all required fields
  - Validates issue structure
  - Fails fast on invalid responses (no silent failures)
- **Enhanced**: Azure DevOps Client
  - Added race condition protection with async locks
  - Added retry logic with exponential backoff
  - Automatic token refresh for Managed Identity
  - Improved error handling and logging

### Fixed
- **Security Fixes**
  - Fixed webhook authentication bypass vulnerability
  - Fixed input validation gaps (payload size, JSON depth)
  - Fixed file path traversal vulnerability
  - Fixed error information leakage
  - Fixed type hint issue (obj: any → obj: Any)
- **Reliability Fixes**
  - Fixed race condition in session management
  - Fixed table storage error handling (fail fast instead of silent)
  - Fixed missing timeouts on AI API calls
  - Fixed asyncio import location in ai_client.py
- **Code Quality Fixes**
  - Fixed deprecated datetime.utcnow() usage (Python 3.12+ compatibility)
  - Fixed magic numbers throughout codebase
  - Fixed missing docstrings on private methods
  - Fixed inconsistent error handling patterns

### Removed
- Development environment webhook bypass (security improvement)
- Connection string requirement for Table Storage
- PAT token authentication (Managed Identity only)

### Security
- All authentication uses Managed Identity (credential-free)
- Azure DevOps: Managed Identity only (no PAT fallback)
- Table Storage: Managed Identity with RBAC roles
- Key Vault: Managed Identity access
- Zero credentials in configuration files or code
- Enhanced input validation on all endpoints
- Comprehensive security documentation added

## [1.3.0] - 2024-12-15

### Added
- Initial release with PAT token authentication
- Basic PR review functionality
- OpenAI/Azure OpenAI integration
- Diff parsing and analysis
- Azure DevOps webhook support

## Migration Guide

### Upgrading from 1.x to 2.0

1. **Enable Managed Identity** on your Function App
2. **Grant permissions** to Key Vault and Table Storage
3. **Update app settings**:
   - Remove: `AZURE_STORAGE_CONNECTION_STRING`
   - Add: `AZURE_STORAGE_ACCOUNT_NAME`
4. **Add MI to Azure DevOps organization** (optional, for PAT-free auth)
5. **Update dependencies**: `pip install -r requirements.txt`
6. **Test deployment** and verify logs show `method="managed_identity"`

See `docs/MANAGED-IDENTITY-SETUP.md` and `docs/AZURE-DEVOPS-MANAGED-IDENTITY.md` for detailed migration steps.

### Breaking Changes

- Configuration changes required (see above)
- Health endpoint now requires authentication
- Python 3.12+ required for datetime compatibility

[2.0.0]: https://github.com/yourusername/CodeWarden/releases/tag/v2.0.0
[1.3.0]: https://github.com/yourusername/CodeWarden/releases/tag/v1.3.0
