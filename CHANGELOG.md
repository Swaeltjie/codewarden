# Changelog

All notable changes to CodeWarden will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

### Fixed - Critical Bug Fixes

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
