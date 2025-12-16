# src/utils/constants.py
"""
Application Constants

Centralized constants to avoid magic numbers throughout the codebase.
All magic numbers and configuration values should be defined here.

Version: 2.8.1 - Added MAX_FEEDBACK_ENTRIES query limit
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
# Large prompts (14K+ tokens) and advanced models need extended timeout
AI_CLIENT_TIMEOUT = 180

# Timeout for AI API request completion (includes response generation)
# Large prompts (14K+ tokens) and advanced models need extended timeout
AI_REQUEST_TIMEOUT = 180

# =============================================================================
# AZURE DEVOPS API SETTINGS
# =============================================================================

# End-of-line offset for inline comments in Azure DevOps thread context
# Using a large value (999) to ensure the comment covers the entire line
# regardless of actual line length, as Azure DevOps API doesn't provide
# a "rest of line" semantic
AZURE_DEVOPS_LINE_END_OFFSET = 999

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

# Exponential backoff multiplier for retry delays
RETRY_BACKOFF_MULTIPLIER = 1

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
# NOTE: Update these values based on your actual model pricing
# =============================================================================

# Approximate cost per 1K prompt tokens
COST_PER_1K_PROMPT_TOKENS = 0.01

# Approximate cost per 1K completion tokens
COST_PER_1K_COMPLETION_TOKENS = 0.03

# =============================================================================
# TABLE STORAGE
# =============================================================================

# List of Azure Table Storage tables required by the application
REQUIRED_TABLES = ["feedback", "reviewhistory", "idempotency", "responsecache"]

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
# IMPORTANT: Must be >= CACHE_TTL_DAYS * 24 to prevent duplicates with cached responses
IDEMPOTENCY_TTL_HOURS = 72  # 3 days - matches cache TTL

# Table name for storing idempotency keys
IDEMPOTENCY_TABLE_NAME = "idempotency"

# Minimum days for idempotency statistics query
IDEMPOTENCY_STATS_MIN_DAYS = 1

# Maximum days for idempotency statistics query
IDEMPOTENCY_STATS_MAX_DAYS = 365

# Default days for idempotency statistics query
IDEMPOTENCY_STATS_DEFAULT_DAYS = 7

# =============================================================================
# RESPONSE CACHE SETTINGS
# =============================================================================

# Days to cache AI responses (aligned with feedback collection window)
CACHE_TTL_DAYS = 3

# Table name for storing cached responses
CACHE_TABLE_NAME = "responsecache"

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

# Timeout for async operations that need quick failure (seconds)
ASYNC_OPERATION_TIMEOUT_SECONDS = 5

# Timeout for blocking table storage operations (seconds)
TABLE_STORAGE_OPERATION_TIMEOUT_SECONDS = 30

# Polling delay when waiting for async operations (seconds)
ASYNC_POLL_DELAY_SECONDS = 0.250

# =============================================================================
# FEEDBACK TRACKING SETTINGS
# =============================================================================

# Table name for storing developer feedback
FEEDBACK_TABLE_NAME = "feedback"

# Hours to look back when collecting feedback from PR threads
FEEDBACK_COLLECTION_HOURS = 24

# Minimum feedback samples required for statistical significance
FEEDBACK_MIN_SAMPLES = 5

# Positive feedback rate threshold for "high value" issue types (>70%)
FEEDBACK_HIGH_VALUE_THRESHOLD = 0.7

# Positive feedback rate threshold for "low value" issue types (<30%)
FEEDBACK_LOW_VALUE_THRESHOLD = 0.3

# =============================================================================
# FEEDBACK LEARNING SETTINGS (v2.7.0)
# =============================================================================

# Maximum few-shot examples per issue type in learning context
MAX_EXAMPLES_PER_ISSUE_TYPE = 3

# Maximum total examples to include in prompt (prevents token bloat)
MAX_TOTAL_EXAMPLES_IN_PROMPT = 10

# Maximum code snippet length in examples (characters)
MAX_EXAMPLE_CODE_SNIPPET_LENGTH = 500

# Maximum suggestion text length in examples (characters)
MAX_EXAMPLE_SUGGESTION_LENGTH = 300

# Days to look back for extracting few-shot examples
LEARNING_CONTEXT_DAYS = 90

# Minimum acceptance rate for an example to be considered "high quality"
MIN_EXAMPLE_QUALITY_RATE = 0.8

# Maximum rejection patterns to include in prompt
MAX_REJECTION_PATTERNS = 5

# Minimum rejections before a pattern is considered significant
MIN_REJECTIONS_FOR_PATTERN = 3

# Maximum characters for enhanced learning section (prevents prompt bloat)
MAX_LEARNING_SECTION_LENGTH = 10000

# Maximum JSON field size for feedback parsing (DoS protection)
MAX_JSON_FIELD_SIZE = 10000

# =============================================================================
# REVIEW HISTORY SETTINGS
# =============================================================================

# Table name for storing review history
REVIEW_HISTORY_TABLE_NAME = "reviewhistory"

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
# Modern models support 128K+ output tokens - use maximum capacity
DEFAULT_MAX_TOKENS = 128000

# =============================================================================
# LOGGING
# =============================================================================

# Default logging level for the application
DEFAULT_LOG_LEVEL = "INFO"

# =============================================================================
# FILE TYPE REGISTRY
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

# =============================================================================
# CONTEXT MANAGER / REVIEW STRATEGY
# =============================================================================

# Maximum lines per file for token estimation (prevents integer overflow)
MAX_LINES_PER_FILE = 100_000

# Maximum tokens per file (caps token estimation)
MAX_TOKENS_PER_FILE = 1_000_000

# Strategy thresholds for determining review approach
STRATEGY_SMALL_FILE_LIMIT = 5  # Max files for single-pass review
STRATEGY_SMALL_TOKEN_LIMIT = 10_000  # Max tokens for single-pass review
STRATEGY_MEDIUM_FILE_LIMIT = 15  # Max files for chunked review
STRATEGY_MEDIUM_TOKEN_LIMIT = 40_000  # Max tokens for chunked review

# Tokens per line estimate for code files
TOKENS_PER_LINE_ESTIMATE = 6

# =============================================================================
# DIFF PARSING
# =============================================================================

# Maximum lines in a single hunk (DoS protection)
MAX_HUNK_LINES = 10_000

# Maximum lines in a diff file (DoS protection for fallback parser)
MAX_DIFF_LINES = 100_000

# =============================================================================
# REVIEW RESULT LIMITS
# =============================================================================

# Maximum individual issue errors to log before summarizing
MAX_LOGGED_ISSUE_ERRORS = 10

# Maximum aggregated tokens value (Pydantic field limit protection)
MAX_AGGREGATED_TOKENS = 9_999_999

# Maximum aggregated cost value (Pydantic field limit protection)
MAX_AGGREGATED_COST = 9_999.99

# =============================================================================
# QUERY LIMITS
# =============================================================================

# Maximum entries to process in idempotency statistics query
MAX_IDEMPOTENCY_ENTRIES = 10_000

# Maximum reviews to process in pattern detection query
MAX_PATTERN_REVIEWS = 10_000

# Maximum feedback entries to process in queries (prevents memory exhaustion)
MAX_FEEDBACK_ENTRIES = 10_000

# =============================================================================
# INTERACTIVE COMMENTS SETTINGS (v2.8.0)
# =============================================================================

# Maximum documentation links per issue
MAX_DOCUMENTATION_LINKS_PER_ISSUE = 5

# Maximum impact description length
MAX_IMPACT_LENGTH = 2000

# Maximum rule ID length
MAX_RULE_ID_LENGTH = 50

# Trusted documentation domains for Learn More links
TRUSTED_DOCUMENTATION_DOMAINS = [
    "docs.microsoft.com",
    "learn.microsoft.com",
    "owasp.org",
    "cheatsheetseries.owasp.org",
    "github.com",
    "registry.terraform.io",
    "kubernetes.io",
    "docker.com",
    "aws.amazon.com",
    "cloud.google.com",
]

# Environment variable for CodeWarden action endpoints base URL
CODEWARDEN_ACTIONS_BASE_URL_SETTING = "CODEWARDEN_ACTIONS_BASE_URL"
