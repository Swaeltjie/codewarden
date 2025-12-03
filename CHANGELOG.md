# Changelog

All notable changes to CodeWarden will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
