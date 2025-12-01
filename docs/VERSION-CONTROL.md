# Version Control & Changelog

## Current Version: 2.5.0 (Production Ready)

**Release Date:** 2025-12-01
**Status:** ✅ Production Ready (Reliability & Observability)

---

## Version History

### v2.5.0 - Reliability & Observability (2025-12-01)

**Minor Release** - Reliability improvements and observability enhancements

#### ✅ Critical Fixes

**CACHE_TTL_DAYS in Settings:**
- ✅ Added `CACHE_TTL_DAYS` to Settings class properly
- ✅ Response cache now uses settings value directly
- ✅ No more `getattr()` workaround needed

**Error Context in Parallel Operations:**
- ✅ Custom wrapper functions preserve error context
- ✅ Partial failures logged with file path and error type
- ✅ Semaphore-limited concurrency for all parallel ops

**Timer Trigger Retry Logic:**
- ✅ Configurable retry with `TIMER_MAX_RETRIES=3`
- ✅ `TIMER_RETRY_DELAY_SECONDS=30` between attempts
- ✅ Both feedback collector and pattern detector triggers

#### ✅ High Priority

**Deprecated Session Property Removed:**
- ✅ Removed sync `session` property from AzureDevOpsClient
- ✅ All callers must use `await _get_session()`

**Centralized Version Management:**
- ✅ Single source: `src/utils/config.py:__version__`
- ✅ All modules and endpoints use centralized version

#### ✅ Medium Priority

**Circuit Breaker Admin Endpoint:**
- ✅ New `/api/circuit-breaker-admin` POST endpoint
- ✅ Reset all or specific circuit breakers
- ✅ Get current status of all breakers

**PatternDetector Metrics:**
- ✅ `PatternDetectorMetrics` dataclass for observability
- ✅ Tracks duration, repositories, patterns, errors
- ✅ `last_metrics` property for access

**Concurrency Limiting:**
- ✅ `MAX_CONCURRENT_REVIEWS=10` setting
- ✅ Semaphore applied to diff fetching and reviews
- ✅ Prevents overwhelming external APIs

**Result Aggregation Validation:**
- ✅ Filters None values before aggregation
- ✅ Type checking for ReviewResult instances
- ✅ Logs skipped invalid results

---

### v2.4.0 - Phase 2 Learning & Developer Experience (2025-12-01)

**Minor Release** - Learning context integration and developer experience improvements

#### ✅ Phase 2 Learning System

**Learning Context Integration:**
- ✅ AI prompts include team preference context from feedback
- ✅ High-value issue types prioritized (>70% acceptance)
- ✅ Low-value issue types de-prioritized (<30% acceptance)
- ✅ `_build_learning_context_section()` in prompts/factory.py

**SuggestedFix Model:**
- ✅ New Pydantic model with before/after code
- ✅ `suggested_fix` field in ReviewIssue
- ✅ Copy-pasteable solutions for developers

#### ✅ Developer Experience

**Dry-Run Mode:**
- ✅ `DRY_RUN=true` environment variable
- ✅ Full workflow without posting comments
- ✅ Useful for testing and development

**Function-Level Timeout:**
- ✅ 8-minute timeout protection (480s)
- ✅ Graceful 504 response for long reviews
- ✅ Buffer before Azure's 10-min limit

**Unit Tests:**
- ✅ Comprehensive webhook handler tests
- ✅ Strategy selection, dry-run, aggregation
- ✅ File path validation tests

#### ✅ Critical Fixes

**Removed Unused Dependencies:**
- ✅ Removed `anthropic==0.40.0`
- ✅ Reduces attack surface

**Exception Handling:**
- ✅ Replaced bare exceptions with specific types
- ✅ Context preserved in error logs

**File Path Validation:**
- ✅ Pydantic field_validator
- ✅ Rejects path traversal, null bytes

---

### v2.3.0 - Security & Performance Improvements (2025-12-01)

**Minor Release** - Critical bug fixes and performance enhancements

#### ✅ Critical Bug Fixes

**Circuit Breaker Infinite Wait:**
- ✅ Added 30-second timeout on lock acquisition
- ✅ Prevents indefinite blocking when lock is held
- ✅ Proper lock release with try/finally blocks

**Missing asyncio Import:**
- ✅ Added `import asyncio` to ai_client.py
- ✅ Fixes `asyncio.wait_for` usage in API timeout handling

#### ✅ New Features

**Rate Limiting:**
- ✅ Sliding window rate limiter (100 req/min per IP)
- ✅ Proper 429 responses with Retry-After header
- ✅ X-Forwarded-For support for load balancers

**Connection Pool Tuning:**
- ✅ Custom TCPConnector for Azure DevOps client
- ✅ 100 connections total, 30 per-host limit
- ✅ DNS caching with 5-minute TTL

**Resource Cleanup:**
- ✅ atexit handler for shutdown cleanup
- ✅ SecretManager credential cleanup
- ✅ Prevents resource leaks

---

### v2.2.0 - Reliability Enhancements (2025-11-30)

**Major Release** - Production reliability features

#### ✅ Reliability Features Added

**Request Idempotency:**
- ✅ `IdempotencyChecker` - Prevents duplicate PR review processing
- ✅ Azure Table Storage integration with 48-hour TTL
- ✅ Deterministic request ID generation
- ✅ Integrated into PR webhook handler

**Circuit Breaker Pattern:**
- ✅ `CircuitBreaker` and `CircuitBreakerManager`
- ✅ Three states: CLOSED, OPEN, HALF_OPEN
- ✅ Integrated into OpenAI API client
- ✅ Integrated into Azure DevOps API client
- ✅ Automatic failure detection and recovery

**Response Caching:**
- ✅ `ResponseCache` - SHA256 content-based caching
- ✅ 7-day TTL with automatic expiration
- ✅ 20-30% expected cost savings
- ✅ Integrated into file review workflow

**Monitoring & Observability:**
- ✅ `/api/reliability-health` endpoint
- ✅ Datadog dashboard configuration (17 widgets)
- ✅ Custom metrics for all reliability features
- ✅ Performance benchmark suite (pytest-benchmark)

**Data Models:**
- ✅ `IdempotencyEntity` - Request tracking
- ✅ `CacheEntity` - Response storage
- ✅ `CircuitBreakerState` - State management

#### 📈 Performance Benchmarks
- Diff parsing: <1ms (small), <10ms (medium), <100ms (large)
- Cache operations: <1ms for hash generation
- Idempotency checks: <0.1ms for request ID generation
- Circuit breaker: <0.1ms state checking overhead

#### 💰 Cost Impact
- **Savings**: 20-30% reduction in AI API costs (caching)
- **Additional**: ~$0.10/month Table Storage overhead
- **Net**: Significant savings with minimal cost

### v2.0.0 - Production Ready Release (2025-11-30)

**Major Release** - Complete implementation with all core services

#### ✅ Implemented Features

**Core Services (NEW):**
- ✅ `azure_devops.py` - Full Azure DevOps REST API client
  - Get PR details
  - Fetch file diffs
  - Post summary comments
  - Post inline comments
  - Retry logic and error handling
  
- ✅ `ai_client.py` - OpenAI integration with retry logic
  - Automatic rate limit handling (exponential backoff)
  - Structured JSON response parsing
  - Token counting and cost estimation
  - Error handling for all failure modes

- ✅ `models/pr_event.py` - Type-safe Pydantic models
  - PREvent with Azure DevOps webhook parsing
  - FileChange with diff analysis
  - FileType enum

- ✅ `models/review_result.py` - Review result models
  - ReviewResult with aggregation
  - ReviewIssue with severity levels
  - Hierarchical aggregation support

**Utilities (NEW):**
- ✅ `utils/config.py` - Configuration management
  - Settings from environment
  - Azure Key Vault integration
  - Secret caching for performance

- ✅ `utils/logging.py` - Structured logging
  - Datadog integration via ddtrace
  - JSON output for log aggregation
  - Context binding (correlation IDs, pr_id, etc.)

- ✅ `utils/table_storage.py` - Table Storage helpers
  - Connection pooling
  - Table creation helpers
  - Query utilities

**Supporting Services (NEW):**
- ✅ `context_manager.py` - Review strategy selection
  - Single-pass for small PRs
  - Chunked for medium PRs
  - Hierarchical for large PRs

- ✅ `comment_formatter.py` - Markdown formatting
  - Summary comments with statistics
  - Inline comments for specific lines
  - Severity icons and formatting

- ✅ `prompts/factory.py` - AI prompt generation
  - File-type specific instructions
  - Diff-only analysis integration
  - Learning context integration

**Phase 2 Stubs (NEW):**
- ✅ `feedback_tracker.py` - Stub for Phase 2
- ✅ `pattern_detector.py` - Stub for Phase 2

#### 🐛 Fixed Issues

**Critical Fixes:**
1. ✅ Fixed logging inconsistency (structlog + Datadog)
2. ✅ Implemented all missing service files
3. ✅ Fixed health check to reference table_storage
4. ✅ Removed OpenTelemetry dependencies (App Insights)
5. ✅ Fixed PREvent type mismatch (attribute vs dict access)
6. ✅ Added proper Azure DevOps webhook validation

**High Priority Fixes:**
7. ✅ Added webhook event type validation
8. ✅ Added proper error handling for missing fields
9. ✅ Updated requirements.txt (added azure-data-tables)
10. ✅ Created all __init__.py files for proper imports

**Dependencies Updated:**
- ✅ Added `azure-data-tables==12.4.0`
- ✅ Removed `azure-monitor-opentelemetry`
- ✅ Removed `opentelemetry-*` packages
- ✅ Kept `ddtrace` and `datadog` for monitoring
- ✅ Kept `structlog` for structured logging

#### 📚 Documentation Updates

- ✅ Updated all version numbers to 2.0.0
- ✅ Created COMPREHENSIVE-AUDIT.md
- ✅ Created IMPLEMENTATION-ROADMAP.md
- ✅ Created this VERSION-CONTROL.md
- ✅ Updated README.md with Python 3.12
- ✅ Updated all guides to reference Datadog

#### 🔄 Breaking Changes

None - First production release

---

### v1.3.0 - Architecture Enhancement (2025-11-29)

**Feature Release** - Added diff-only analysis and learning features

#### Added
- Diff-only analysis (50-85% token savings)
- Feedback tracking system design
- Historical pattern detection design
- Human decision framework
- Blocking vs non-blocking issue classification

#### Documentation
- Complete architecture document
- Gap analysis
- Enhancement proposals
- Quick answers guide

---

### v1.2.0 - Python Migration (2025-11-29)

**Major Change** - Switched from C# to Python

#### Changed
- Runtime: .NET 8 → Python 3.12
- Monitoring: Application Insights → Datadog
- Storage: Cosmos DB → Azure Table Storage

#### Added
- Python vs C# comparison analysis
- Python best practices guide
- Datadog integration guide
- Complete cost analysis

#### Rationale
- Better AI/ML library support
- Faster development iteration
- Superior text processing
- Team preference
- Cost savings ($2-5/month on monitoring)

---

### v1.1.0 - Initial Design (2025-11-28)

**Initial Release** - Architecture and design

#### Added
- System architecture
- Technology selection
- Cost estimates
- Deployment strategy
- Scalability analysis

---

## Version Numbering

We use Semantic Versioning (SemVer): `MAJOR.MINOR.PATCH`

- **MAJOR**: Breaking changes or major feature releases
- **MINOR**: New features, backwards compatible
- **PATCH**: Bug fixes, backwards compatible

---

## Component Versions

### Core Components

| Component | Version | Status | Notes |
|-----------|---------|--------|-------|
| function_app.py | 2.5.0 | ✅ Ready | Main entry point |
| azure_devops.py | 2.5.0 | ✅ Ready | DevOps API client |
| ai_client.py | 1.0.0 | ✅ Ready | OpenAI integration |
| diff_parser.py | 1.0.0 | ✅ Ready | Git diff parsing |
| pr_webhook.py | 2.5.0 | ✅ Ready | Webhook handler |

### Models

| Component | Version | Status | Notes |
|-----------|---------|--------|-------|
| pr_event.py | 1.0.0 | ✅ Ready | PR event models |
| review_result.py | 2.5.0 | ✅ Ready | Review result models |

### Utilities

| Component | Version | Status | Notes |
|-----------|---------|--------|-------|
| config.py | 2.5.0 | ✅ Ready | Configuration & version |
| logging.py | 1.0.0 | ✅ Ready | Logging setup |
| table_storage.py | 1.0.0 | ✅ Ready | Table Storage |

### Services

| Component | Version | Status | Notes |
|-----------|---------|--------|-------|
| context_manager.py | 1.0.0 | ✅ Ready | Strategy selection |
| comment_formatter.py | 1.0.0 | ✅ Ready | Markdown formatting |
| prompts/factory.py | 1.0.0 | ✅ Ready | Prompt generation |
| feedback_tracker.py | 2.5.0 | ✅ Production | Feedback tracking & learning |
| pattern_detector.py | 2.5.0 | ✅ Production | Pattern analysis with metrics |
| circuit_breaker.py | 2.5.0 | ✅ Production | Circuit breaker with admin endpoint |
| response_cache.py | 2.5.0 | ✅ Production | Response caching |

### Documentation

| Document | Version | Status |
|----------|---------|--------|
| README.md | 2.0.0 | ✅ Current |
| ARCHITECTURE.md | 2.0.0 | ✅ Current |
| DEPLOYMENT-GUIDE.md | 2.0.0 | ✅ Current |
| BEST-PRACTICES-SUMMARY.md | 2.0.0 | ✅ Current |
| DATADOG-INTEGRATION.md | 1.0.0 | ✅ Current |
| COMPREHENSIVE-AUDIT.md | 1.0.0 | ✅ Current |
| IMPLEMENTATION-ROADMAP.md | 1.0.0 | ✅ Current |

---

## Upgrade Path

### From v1.3.0 (Architecture Only) → v2.0.0 (Full Implementation)

**What's New:**
- All core services implemented
- Production-ready code
- Complete error handling
- Datadog integration
- Table Storage utilities

**Migration Steps:**
1. Deploy all new service files
2. Update environment variables
3. Configure Datadog API key
4. Test with sample PR
5. Monitor logs in Datadog

**No breaking changes** - This is the first implementation

---

## Roadmap

### v2.1.0 - Phase 2 Features ✅ COMPLETED (2025-11-30)
**Production-Ready Continuous Learning System**

- ✅ Implemented feedback tracking
- ✅ Implemented pattern detection
- ✅ Added learning system (team preferences)
- ✅ Added repository health scoring
- ✅ Added comprehensive integration tests
- ✅ Team-specific customization via learning context

### v2.2.0 - Reliability Enhancements ✅ COMPLETED (2025-11-30)
**Production-Ready Reliability Features**

- ✅ Added request idempotency (IdempotencyChecker)
- ✅ Added circuit breaker pattern (CircuitBreaker, CircuitBreakerManager)
- ✅ Implemented response caching (ResponseCache with SHA256 hashing)
- ✅ Added performance benchmarks (pytest-benchmark suite)
- ✅ Enhanced monitoring dashboards (Datadog with 17 widgets)
- ✅ Created reliability health endpoint (/api/reliability-health)
- ✅ Integrated all features into production workflow

### v3.0.0 - Advanced Features (Future)
**Target: 2-3 months**

- Multi-model support (Claude, Gemini)
- Custom rule engine
- Advanced caching
- Performance optimizations
- Multi-region deployment

---

## Deprecation Policy

We follow a conservative deprecation policy:

1. **Deprecation Notice**: Feature marked as deprecated in docs
2. **Grace Period**: Minimum 2 minor versions or 60 days
3. **Removal**: Feature removed in next major version

**Currently Deprecated:** None

---

## Support Matrix

### Python Versions

| Version | Status | Support Until |
|---------|--------|---------------|
| 3.12 | ✅ Supported | Current |
| 3.11 | ⚠️ Works but not tested | - |
| 3.10 | ❌ Not supported | - |

### Azure Functions Runtime

| Version | Status | Support Until |
|---------|--------|---------------|
| 4.x | ✅ Supported | Current |
| 3.x | ❌ Not supported | - |

### Azure DevOps API

| Version | Status | Support Until |
|---------|--------|---------------|
| 7.0 | ✅ Supported | Current |
| 6.0 | ⚠️ May work | - |

---

## Release Checklist

Before releasing a new version:

- [ ] All tests passing
- [ ] Documentation updated
- [ ] Version numbers updated in all files
- [ ] Changelog updated
- [ ] Security scan passed
- [ ] Code review completed
- [ ] Deployment tested in staging
- [ ] Rollback plan documented

---

## Contact & Support

**Issues:** Report via Azure DevOps issues  
**Questions:** Contact DevOps team  
**Emergency:** On-call rotation

---

**Last Updated:** 2025-11-30  
**Maintained By:** DevOps Team  
**License:** Internal Use Only
