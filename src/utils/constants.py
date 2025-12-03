# src/utils/constants.py
"""
Application Constants

Centralized constants to avoid magic numbers throughout the codebase.
All magic numbers and configuration values should be defined here.

Version: 2.6.0 - Universal code review
"""

# =============================================================================
# FUNCTION APP SETTINGS
# =============================================================================

# Maximum function execution time before timeout
# Azure Functions have a 10-minute limit; we use 8 minutes as a safety buffer
FUNCTION_TIMEOUT_SECONDS = 480

# =============================================================================
# WEBHOOK VALIDATION
# =============================================================================

# Maximum allowed webhook payload size to prevent memory exhaustion attacks
MAX_PAYLOAD_SIZE_BYTES = 1024 * 1024  # 1MB

# Maximum nesting depth for JSON payloads to prevent stack overflow attacks
MAX_JSON_DEPTH = 10

# =============================================================================
# RATE LIMITING
# =============================================================================

# Maximum number of requests allowed within the sliding window
RATE_LIMIT_MAX_REQUESTS = 100

# Duration of the sliding window for rate limiting (in seconds)
RATE_LIMIT_WINDOW_SECONDS = 60

# =============================================================================
# API TIMEOUTS (in seconds)
# =============================================================================

# Timeout for Azure DevOps API calls (get PR, post comments, etc.)
AZURE_DEVOPS_TIMEOUT = 30

# Timeout for establishing connection to AI service
AI_CLIENT_TIMEOUT = 60

# Timeout for AI API request completion (includes response generation)
AI_REQUEST_TIMEOUT = 90

# =============================================================================
# HTTP CONNECTION POOL SETTINGS
# =============================================================================

# Total connection pool size for HTTP clients
HTTP_CONNECTION_POOL_SIZE = 100

# Maximum connections per host (prevents overwhelming single endpoint)
HTTP_CONNECTION_LIMIT_PER_HOST = 30

# DNS cache TTL in seconds (reduces DNS lookup overhead)
DNS_CACHE_TTL_SECONDS = 300

# =============================================================================
# LOGGING SETTINGS
# =============================================================================

# Maximum length for log field values (prevents log bloat)
LOG_FIELD_MAX_LENGTH = 100

# =============================================================================
# AI CLIENT SETTINGS
# =============================================================================

# Maximum prompt length in characters (~250K tokens)
# Prevents excessive token usage and API errors
MAX_PROMPT_LENGTH = 1_000_000

# Default delay before retrying after a rate limit response
DEFAULT_RETRY_AFTER_SECONDS = 60

# =============================================================================
# RETRY CONFIGURATION
# =============================================================================

# Maximum number of retry attempts for transient failures
MAX_RETRY_ATTEMPTS = 3

# Minimum wait time between retries (exponential backoff base)
RETRY_MIN_WAIT_SECONDS = 2

# Maximum wait time between retries (exponential backoff cap)
RETRY_MAX_WAIT_SECONDS = 10

# =============================================================================
# TOKEN ESTIMATION
# =============================================================================

# Approximate characters per token for quick estimation before tiktoken
# GPT models average ~4 chars/token for code
CHARS_PER_TOKEN_ESTIMATE = 4

# =============================================================================
# DIFF PARSING
# =============================================================================

# Number of context lines to include around changes in diff output
DEFAULT_CONTEXT_LINES = 3

# =============================================================================
# PROMPT FACTORY INPUT LIMITS (DoS Protection)
# =============================================================================

# Maximum length for PR titles to prevent prompt injection
PROMPT_MAX_TITLE_LENGTH = 500

# Maximum length for file paths in prompts
PROMPT_MAX_PATH_LENGTH = 1000

# Maximum length for commit messages in prompts
PROMPT_MAX_MESSAGE_LENGTH = 5000

# Maximum length for issue type identifiers
PROMPT_MAX_ISSUE_TYPE_LENGTH = 100

# =============================================================================
# REVIEW LIMITS
# =============================================================================

# Maximum files to review in a single PR (performance/cost guard)
MAX_FILES_PER_REVIEW = 50

# Maximum issues to report per review (prevent overwhelming feedback)
MAX_ISSUES_PER_REVIEW = 100

# Azure DevOps maximum comment length (API limit)
MAX_COMMENT_LENGTH = 65536

# =============================================================================
# COST ESTIMATION (USD per 1K tokens)
# =============================================================================

# Approximate cost per 1K prompt tokens (GPT-4 Turbo pricing)
COST_PER_1K_PROMPT_TOKENS = 0.01

# Approximate cost per 1K completion tokens (GPT-4 Turbo pricing)
COST_PER_1K_COMPLETION_TOKENS = 0.03

# =============================================================================
# TABLE STORAGE
# =============================================================================

# List of Azure Table Storage tables required by the application
REQUIRED_TABLES = ['feedback', 'reviewhistory', 'idempotency', 'responsecache']

# Number of retry attempts for Table Storage operations
TABLE_STORAGE_RETRY_ATTEMPTS = 3

# Minimum wait between Table Storage retries (seconds)
TABLE_STORAGE_RETRY_MIN_WAIT = 2

# Maximum wait between Table Storage retries (seconds)
TABLE_STORAGE_RETRY_MAX_WAIT = 10

# Page size for paginated Table Storage queries
TABLE_STORAGE_BATCH_SIZE = 100

# =============================================================================
# IDEMPOTENCY SETTINGS
# =============================================================================

# Hours to keep idempotency records (prevents duplicate processing)
IDEMPOTENCY_TTL_HOURS = 48

# Table name for storing idempotency keys
IDEMPOTENCY_TABLE_NAME = 'idempotency'

# =============================================================================
# RESPONSE CACHE SETTINGS
# =============================================================================

# Days to cache AI responses (aligned with feedback collection window)
CACHE_TTL_DAYS = 3

# Table name for storing cached responses
CACHE_TABLE_NAME = 'responsecache'

# Rate limit for cache writes to prevent storage throttling
CACHE_MAX_WRITES_PER_MINUTE = 100

# =============================================================================
# CIRCUIT BREAKER SETTINGS
# =============================================================================

# Number of consecutive failures before circuit opens
DEFAULT_CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5

# Seconds to wait before attempting recovery (half-open state)
DEFAULT_CIRCUIT_BREAKER_TIMEOUT_SECONDS = 60

# Successful requests needed in half-open state to close circuit
DEFAULT_CIRCUIT_BREAKER_SUCCESS_THRESHOLD = 2

# Maximum time to wait for acquiring circuit breaker lock
CIRCUIT_BREAKER_LOCK_TIMEOUT_SECONDS = 30

# =============================================================================
# FEEDBACK TRACKING SETTINGS
# =============================================================================

# Table name for storing developer feedback
FEEDBACK_TABLE_NAME = 'feedback'

# Hours to look back when collecting feedback from PR threads
FEEDBACK_COLLECTION_HOURS = 24

# Minimum feedback samples required for statistical significance
FEEDBACK_MIN_SAMPLES = 5

# Positive feedback rate threshold for "high value" issue types (>70%)
FEEDBACK_HIGH_VALUE_THRESHOLD = 0.7

# Positive feedback rate threshold for "low value" issue types (<30%)
FEEDBACK_LOW_VALUE_THRESHOLD = 0.3

# =============================================================================
# REVIEW HISTORY SETTINGS
# =============================================================================

# Table name for storing review history
REVIEW_HISTORY_TABLE_NAME = 'reviewhistory'

# Days to analyze for pattern detection
PATTERN_ANALYSIS_DAYS = 30

# Threshold for marking an issue as "recurring" (appears in >30% of PRs)
PATTERN_RECURRENCE_THRESHOLD = 0.3

# =============================================================================
# PERFORMANCE THRESHOLDS (in seconds)
# Target response times for performance monitoring
# =============================================================================

# Target time for parsing small diffs (<100 lines)
PERF_SMALL_DIFF_TARGET = 0.001  # 1ms

# Target time for parsing medium diffs (100-1000 lines)
PERF_MEDIUM_DIFF_TARGET = 0.01  # 10ms

# Target time for parsing large diffs (>1000 lines)
PERF_LARGE_DIFF_TARGET = 0.1  # 100ms

# Target time for computing cache hash
PERF_CACHE_HASH_TARGET = 0.001  # 1ms

# Target time for idempotency key lookup
PERF_IDEMPOTENCY_TARGET = 0.0001  # 0.1ms

# Target time for circuit breaker state check
PERF_CIRCUIT_BREAKER_TARGET = 0.0001  # 0.1ms

# =============================================================================
# HEALTH CHECK SETTINGS
# =============================================================================

# Cache efficiency below this percentage is "low"
HEALTH_CHECK_CACHE_EFFICIENCY_LOW = 10

# Cache efficiency below this percentage is "moderate"
HEALTH_CHECK_CACHE_EFFICIENCY_MODERATE = 30

# Duplicate request rate above this percentage is "high"
HEALTH_CHECK_DUPLICATE_RATE_HIGH = 20

# Duplicate request rate above this percentage is "moderate"
HEALTH_CHECK_DUPLICATE_RATE_MODERATE = 10

# =============================================================================
# REPOSITORY HEALTH SCORING
# Thresholds for categorizing repository health status
# =============================================================================

# Maximum possible health score
HEALTH_SCORE_MAX = 100

# Score threshold for "excellent" health status
HEALTH_SCORE_EXCELLENT = 90

# Score threshold for "healthy" status
HEALTH_SCORE_HEALTHY = 80

# Score threshold for "degraded" status (between healthy and unhealthy)
HEALTH_SCORE_DEGRADED = 70

# Score threshold for "moderate" status
HEALTH_SCORE_MODERATE = 60

# Score threshold for "needs attention" status
HEALTH_SCORE_NEEDS_ATTENTION = 40

# Points deducted for recurring issues in repository
HEALTH_SCORE_RECURRING_PENALTY = 30

# =============================================================================
# AI MODEL CONFIGURATION
# =============================================================================

# Temperature for AI responses (lower = more consistent/focused)
DEFAULT_TEMPERATURE = 0.2

# Maximum tokens for AI completion responses
DEFAULT_MAX_TOKENS = 4096

# =============================================================================
# LOGGING
# =============================================================================

# Default logging level for the application
DEFAULT_LOG_LEVEL = "INFO"

# =============================================================================
# FILE TYPE REGISTRY (v2.6.0 - Universal Code Review)
# =============================================================================

# Default token estimate for unknown file types
DEFAULT_TOKEN_ESTIMATE = 350

# Maximum number of best practice items to include in a single prompt
MAX_BEST_PRACTICES_IN_PROMPT = 20

# LRU cache size for file classification results
FILE_CATEGORY_CACHE_SIZE = 1000

# Maximum security checks to include per file category
MAX_SECURITY_CHECKS_PER_CATEGORY = 5

# Maximum common issues to include per file category
MAX_COMMON_ISSUES_PER_CATEGORY = 5

# Maximum performance tips to include per file category
MAX_PERFORMANCE_TIPS_PER_CATEGORY = 3
