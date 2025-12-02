# src/utils/constants.py
"""
Application Constants

Centralized constants to avoid magic numbers throughout the codebase.

Version: 2.5.9
"""

# Function App Settings
FUNCTION_TIMEOUT_SECONDS = 480  # 8 minutes (buffer before Azure's 10-min limit)

# Webhook validation
MAX_PAYLOAD_SIZE_BYTES = 1024 * 1024  # 1MB
MAX_JSON_DEPTH = 10

# Rate Limiting
RATE_LIMIT_MAX_REQUESTS = 100  # Max requests per window
RATE_LIMIT_WINDOW_SECONDS = 60  # Sliding window duration

# API Timeouts (in seconds)
AZURE_DEVOPS_TIMEOUT = 30
AI_CLIENT_TIMEOUT = 60
AI_REQUEST_TIMEOUT = 90

# AI Client Settings
MAX_PROMPT_LENGTH = 1_000_000  # 1 million chars (~250K tokens max)
DEFAULT_RETRY_AFTER_SECONDS = 60  # Default retry delay for rate limits

# Retry configuration
MAX_RETRY_ATTEMPTS = 3
RETRY_MIN_WAIT_SECONDS = 2
RETRY_MAX_WAIT_SECONDS = 10

# Token estimation
CHARS_PER_TOKEN_ESTIMATE = 4  # Rough approximation before tiktoken

# Diff parsing
DEFAULT_CONTEXT_LINES = 3

# Prompt Factory Input Limits (DoS protection)
PROMPT_MAX_TITLE_LENGTH = 500
PROMPT_MAX_PATH_LENGTH = 1000
PROMPT_MAX_MESSAGE_LENGTH = 5000
PROMPT_MAX_ISSUE_TYPE_LENGTH = 100

# Review limits
MAX_FILES_PER_REVIEW = 50
MAX_ISSUES_PER_REVIEW = 100
MAX_COMMENT_LENGTH = 65536  # Azure DevOps max comment length

# Cost estimation (USD per 1K tokens)
# These are approximate rates for GPT-4 Turbo
COST_PER_1K_PROMPT_TOKENS = 0.01
COST_PER_1K_COMPLETION_TOKENS = 0.03

# Table storage
REQUIRED_TABLES = ['feedback', 'reviewhistory', 'idempotency', 'responsecache']

# Idempotency Settings
IDEMPOTENCY_TTL_HOURS = 48
IDEMPOTENCY_TABLE_NAME = 'idempotency'

# Response Cache Settings
CACHE_TTL_DAYS = 3  # Aligned with 24h feedback window (v2.4.0)
CACHE_TABLE_NAME = 'responsecache'
CACHE_MAX_WRITES_PER_MINUTE = 100  # Rate limit for cache writes

# Circuit Breaker Settings
DEFAULT_CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5
DEFAULT_CIRCUIT_BREAKER_TIMEOUT_SECONDS = 60
DEFAULT_CIRCUIT_BREAKER_SUCCESS_THRESHOLD = 2
CIRCUIT_BREAKER_LOCK_TIMEOUT_SECONDS = 30  # Max wait time for lock acquisition

# Feedback Tracking Settings
FEEDBACK_TABLE_NAME = 'feedback'
FEEDBACK_COLLECTION_HOURS = 24
FEEDBACK_MIN_SAMPLES = 5  # Minimum samples for statistical significance
FEEDBACK_HIGH_VALUE_THRESHOLD = 0.7  # >70% positive rate
FEEDBACK_LOW_VALUE_THRESHOLD = 0.3   # <30% positive rate

# Review History Settings
REVIEW_HISTORY_TABLE_NAME = 'reviewhistory'
PATTERN_ANALYSIS_DAYS = 30
PATTERN_RECURRENCE_THRESHOLD = 0.3  # Issue in >30% of PRs

# Performance Thresholds (in seconds)
PERF_SMALL_DIFF_TARGET = 0.001   # 1ms
PERF_MEDIUM_DIFF_TARGET = 0.01   # 10ms
PERF_LARGE_DIFF_TARGET = 0.1     # 100ms
PERF_CACHE_HASH_TARGET = 0.001   # 1ms
PERF_IDEMPOTENCY_TARGET = 0.0001 # 0.1ms
PERF_CIRCUIT_BREAKER_TARGET = 0.0001  # 0.1ms

# Table Storage Settings
TABLE_STORAGE_RETRY_ATTEMPTS = 3
TABLE_STORAGE_RETRY_MIN_WAIT = 2  # seconds
TABLE_STORAGE_RETRY_MAX_WAIT = 10  # seconds
TABLE_STORAGE_BATCH_SIZE = 100  # For pagination

# Health Check Settings
HEALTH_CHECK_CACHE_EFFICIENCY_LOW = 10  # <10% is low
HEALTH_CHECK_CACHE_EFFICIENCY_MODERATE = 30  # <30% is moderate
HEALTH_CHECK_DUPLICATE_RATE_HIGH = 20  # >20% is high
HEALTH_CHECK_DUPLICATE_RATE_MODERATE = 10  # >10% is moderate

# Repository Health Scoring
HEALTH_SCORE_MAX = 100
HEALTH_SCORE_EXCELLENT = 90  # Threshold for "excellent" status
HEALTH_SCORE_HEALTHY = 80
HEALTH_SCORE_MODERATE = 60
HEALTH_SCORE_NEEDS_ATTENTION = 40
HEALTH_SCORE_RECURRING_PENALTY = 30  # Penalty for recurring issues

# AI Model configuration
DEFAULT_TEMPERATURE = 0.2  # Low temperature for consistent, focused reviews
DEFAULT_MAX_TOKENS = 4096

# Logging
DEFAULT_LOG_LEVEL = "INFO"
