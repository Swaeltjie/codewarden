# CodeWarden Monitoring Setup

Comprehensive monitoring configuration for CodeWarden v2.2.0 reliability features.

## Overview

This directory contains monitoring configurations for:
- **Datadog Dashboards** - Visual monitoring of reliability metrics
- **Alert Configurations** - Proactive alerting for issues
- **Custom Metrics** - Application-specific measurements

## Quick Start

### 1. Import Datadog Dashboard

```bash
# Using Datadog API
export DD_API_KEY="your-api-key"
export DD_APP_KEY="your-app-key"

curl -X POST "https://api.datadoghq.com/api/v1/dashboard" \
  -H "Content-Type: application/json" \
  -H "DD-API-KEY: ${DD_API_KEY}" \
  -H "DD-APPLICATION-KEY: ${DD_APP_KEY}" \
  -d @monitoring/datadog-reliability-dashboard.json
```

Or manually:
1. Log into Datadog
2. Go to Dashboards → New Dashboard
3. Click gear icon → Import Dashboard JSON
4. Paste contents of `datadog-reliability-dashboard.json`
5. Click Import

### 2. Configure Alerts

Import the provided alert configurations:

```bash
# Import all alerts
for alert in monitoring/alerts/*.json; do
  curl -X POST "https://api.datadoghq.com/api/v1/monitor" \
    -H "Content-Type: application/json" \
    -H "DD-API-KEY: ${DD_API_KEY}" \
    -H "DD-APPLICATION-KEY: ${DD_APP_KEY}" \
    -d @"$alert"
done
```

## Dashboard Widgets

### Reliability Metrics

**Circuit Breaker Status**
- Shows number of open circuit breakers
- Alert when any service circuit is open
- Indicates service availability issues

**Cache Hit Rate**
- Current cache efficiency percentage
- Target: >30% for cost savings
- Low hit rate (<10%) indicates cache warming needed

**Cost Savings from Cache**
- Total USD saved by avoiding duplicate AI calls
- Tracks cumulative savings over time

**Idempotency - Duplicate Requests Blocked**
- Count of duplicate webhook requests prevented
- High count (>20% of total) may indicate webhook retry issues

### Performance Metrics

**PR Review Latency (p50, p95, p99)**
- Distribution of review completion times
- p50 target: <30s for small PRs
- p95 target: <60s for medium PRs
- p99 target: <120s for large PRs

**OpenAI API Success Rate**
- Percentage of successful AI API calls
- Target: >99% success rate
- Drops indicate API issues or circuit breaker activation

**Azure DevOps API Success Rate**
- Percentage of successful DevOps API calls
- Target: >99% success rate

### Cost Metrics

**Daily Cost Trend**
- AI API costs per day
- Cache savings overlay
- Helps track ROI of caching

**Tokens Used per Review**
- Average token consumption
- Helps optimize prompt design
- Detect anomalies in token usage

### Quality Metrics

**Issues Found by Severity**
- Top list of issue types
- Tracks most common problems
- Guides review focus areas

**Repository Health Scores**
- Heatmap of repository code quality (0-100)
- Identifies repositories needing attention
- Trending over time

## Custom Metrics

CodeWarden emits the following custom metrics:

### Circuit Breaker Metrics

```python
# Emitted by circuit_breaker.py
codewarden.circuit_breaker.open        # Count of open circuits
codewarden.circuit_breaker.half_open   # Count of half-open circuits
codewarden.circuit_breaker.failure     # Circuit breaker failures
```

### Cache Metrics

```python
# Emitted by response_cache.py
codewarden.cache.hit                   # Cache hits
codewarden.cache.miss                  # Cache misses
codewarden.cache.hit_rate              # Hit rate percentage
codewarden.cache.cost_saved_usd        # Cost saved in USD
codewarden.cache.active_entries        # Active cache entries
```

### Idempotency Metrics

```python
# Emitted by idempotency_checker.py
codewarden.idempotency.duplicate_blocked    # Duplicate requests blocked
codewarden.idempotency.total_requests       # Total requests processed
codewarden.idempotency.duplicate_rate       # Duplicate rate percentage
```

### Review Metrics

```python
# Emitted by pr_webhook.py
codewarden.pr_review.duration          # Review duration in seconds
codewarden.pr_review.completed         # Reviews completed
codewarden.pr_review.failed            # Reviews failed
codewarden.review.issues               # Issues found (by severity)
codewarden.review.tokens_used          # Tokens consumed
codewarden.cost.ai_api                 # AI API cost in USD
```

### API Metrics

```python
# Emitted by ai_client.py and azure_devops.py
codewarden.openai.success              # OpenAI API successes
codewarden.openai.failure              # OpenAI API failures
codewarden.openai.total                # Total OpenAI calls
codewarden.azure_devops.success        # Azure DevOps API successes
codewarden.azure_devops.failure        # Azure DevOps API failures
codewarden.azure_devops.total          # Total DevOps calls
```

### Health Metrics

```python
# Emitted by pattern_detector.py
codewarden.repository.health_score     # Repository health (0-100)
codewarden.pattern.recurring_issues    # Recurring issue count
```

## Alerts

### Critical Alerts

**Circuit Breaker Open (P1)**
- Trigger: Any circuit breaker open for >5 minutes
- Action: Page on-call engineer
- Indicates: External service unavailable

**High Error Rate (P1)**
- Trigger: Error rate >5% for 10 minutes
- Action: Page on-call engineer
- Indicates: Systemic issues

**API Success Rate Drop (P2)**
- Trigger: Success rate <95% for 15 minutes
- Action: Alert team channel
- Indicates: API degradation

### Warning Alerts

**Low Cache Hit Rate (P3)**
- Trigger: Cache hit rate <10% for 30 minutes
- Action: Notify team channel
- Indicates: Cache not effective

**High Duplicate Rate (P3)**
- Trigger: Duplicate request rate >20% for 30 minutes
- Action: Notify team channel
- Indicates: Webhook retry issues

**Slow Review Latency (P3)**
- Trigger: p95 latency >120s for 30 minutes
- Action: Notify team channel
- Indicates: Performance degradation

## Accessing Metrics Programmatically

### Via Reliability Health Endpoint

```bash
# Get full reliability health status
curl -H "x-functions-key: YOUR_FUNCTION_KEY" \
  https://your-app.azurewebsites.net/api/reliability-health

# Get circuit breaker status only
curl -H "x-functions-key: YOUR_FUNCTION_KEY" \
  "https://your-app.azurewebsites.net/api/reliability-health?feature=circuit_breakers"

# Get cache statistics for specific repository
curl -H "x-functions-key: YOUR_FUNCTION_KEY" \
  "https://your-app.azurewebsites.net/api/reliability-health?feature=cache&repository=my-repo"

# Get idempotency statistics (last 7 days)
curl -H "x-functions-key: YOUR_FUNCTION_KEY" \
  "https://your-app.azurewebsites.net/api/reliability-health?feature=idempotency&days=7"
```

### Via Datadog API

```python
from datadog_api_client import ApiClient, Configuration
from datadog_api_client.v1.api.metrics_api import MetricsApi

configuration = Configuration()
with ApiClient(configuration) as api_client:
    api_instance = MetricsApi(api_client)

    # Get cache hit rate over last hour
    response = api_instance.query_metrics(
        query="avg:codewarden.cache.hit_rate{*}",
        from_time=int(time.time()) - 3600,
        to_time=int(time.time())
    )

    print(response)
```

## Troubleshooting

### Dashboard Shows No Data

1. **Check Datadog Agent**: Ensure `ddtrace` is installed and configured
2. **Verify App Settings**: `DD_API_KEY` and `DD_SITE` must be set
3. **Check Logs**: Look for "datadog" in function logs
4. **Test Metric Emission**: Call `/api/reliability-health` to trigger metrics

### Alerts Not Firing

1. **Check Alert Configuration**: Verify thresholds in Datadog UI
2. **Check Notification Channels**: Ensure correct channels configured
3. **Check Metric Availability**: View metric in Metrics Explorer
4. **Check Alert Conditions**: May need to adjust sensitivity

### Cache Hit Rate Always 0%

1. **Check Table Storage**: Verify `responsecache` table exists
2. **Check Permissions**: Managed Identity needs Table Storage access
3. **Check Caching Logic**: Review `response_cache.py` logs
4. **Warm Up Cache**: Wait for duplicate reviews to occur

## Best Practices

### Metric Granularity

- Use 1-minute intervals for real-time monitoring
- Use 1-hour rollups for cost tracking
- Use 1-day rollups for trend analysis

### Alert Fatigue Prevention

- Set appropriate thresholds (not too sensitive)
- Use composite conditions (multiple signals)
- Escalate only critical issues
- Regular alert review and tuning

### Cost Optimization

- Track cost savings from cache
- Monitor token usage trends
- Set cost budgets and alerts
- Review high-cost repositories

### Performance Tracking

- Establish baseline performance
- Track p95/p99 latencies
- Monitor for regressions
- Correlate with code changes

## Integration with CI/CD

Add performance checks to your pipeline:

```yaml
# .github/workflows/performance-check.yml
- name: Check Performance Metrics
  run: |
    # Get current p95 latency
    CURRENT_P95=$(curl "https://your-app.azurewebsites.net/api/reliability-health" | jq '.latency_p95')

    # Fail if >120s
    if [ "$CURRENT_P95" -gt 120 ]; then
      echo "Performance regression detected: p95 latency ${CURRENT_P95}s"
      exit 1
    fi
```

## Support

For issues with monitoring setup:
1. Check [DATADOG-INTEGRATION.md](../docs/DATADOG-INTEGRATION.md)
2. Review Datadog documentation
3. Contact DevOps team

---

**Last Updated:** 2025-11-30
**Version:** 2.2.0
