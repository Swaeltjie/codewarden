# Datadog Integration Guide

## Overview

Integrate CodeWarden with your existing Datadog infrastructure for unified monitoring.

**Benefits:**
- ✅ Use existing Datadog subscription (no additional cost)
- ✅ Unified monitoring across all services
- ✅ Superior dashboards and alerting
- ✅ Team already familiar with tooling

---

## Quick Start (Recommended)

### Option: Datadog Extension

**Easiest setup (15 minutes):**

```bash
# Add Datadog settings to Function App
az functionapp config appsettings set \
  --name func-ai-pr-reviewer \
  --resource-group rg-ai-pr-reviewer \
  --settings \
    DD_API_KEY=your-datadog-api-key \
    DD_SITE=datadoghq.com \
    DD_SERVICE=ai-pr-reviewer \
    DD_ENV=production \
    DD_VERSION=2.2.0 \
    DD_LOGS_INJECTION=true \
    DD_TRACE_ENABLED=true
```

**Update `requirements.txt`:**
```
ddtrace>=2.0.0
datadog>=0.44.0
```

**Deploy:**
```bash
func azure functionapp publish func-ai-pr-reviewer --python
```

---

## Application Setup

### 1. Structured Logging

Update your code to use Datadog-friendly logging:

```python
# src/utils/logging.py already configured for Datadog
import structlog

logger = structlog.get_logger(__name__)

# Logs automatically sent to Datadog
logger.info(
    "pr_review_started",
    pr_id=123,
    repository="terraform-repo",
    file_count=5
)
```

### 2. APM Tracing

Enable automatic tracing:

```python
# function_app.py (already configured)
from ddtrace import tracer, patch_all

# Enable Datadog tracing
patch_all()

# Automatic distributed tracing for all functions
```

### 3. Custom Metrics

Track business metrics:

```python
from datadog import statsd

# Duration tracking
statsd.histogram('ai_pr_reviewer.review.duration', 15.3)

# Counters
statsd.increment('ai_pr_reviewer.review.count', tags=['recommendation:approve'])

# Gauges
statsd.gauge('ai_pr_reviewer.review.file_count', 5)

# Cost tracking
statsd.histogram('ai_pr_reviewer.tokens.cost', 0.012)
```

---

## Dashboards

### Create Custom Dashboard

**Key Metrics to Track:**

1. **PR Review Success Rate**
   - Metric: `ai_pr_reviewer.review.count{recommendation:approve}`
   - Visualization: Query Value

2. **Average Review Duration**
   - Metric: `avg:ai_pr_reviewer.review.duration{*}`
   - Visualization: Timeseries

3. **Token Usage & Cost**
   - Metrics: `sum:ai_pr_reviewer.tokens.used{*}`, `sum:ai_pr_reviewer.tokens.cost{*}`
   - Visualization: Timeseries (bars + line)

4. **Error Rate**
   - Metric: `sum:ai_pr_reviewer.errors{*}.as_count()`
   - Visualization: Query Value with alert threshold

**Dashboard JSON Template:**
```json
{
  "title": "CodeWarden - Performance",
  "widgets": [
    {
      "definition": {
        "title": "PR Review Success Rate",
        "type": "query_value",
        "requests": [{
          "q": "sum:ai_pr_reviewer.review.count{recommendation:approve}.as_count() / sum:ai_pr_reviewer.review.count{*}.as_count() * 100"
        }]
      }
    },
    {
      "definition": {
        "title": "Average Review Duration",
        "type": "timeseries",
        "requests": [{
          "q": "avg:ai_pr_reviewer.review.duration{*}",
          "display_type": "line"
        }]
      }
    }
  ]
}
```

---

## Alerts

### Recommended Alert Configuration

**1. High Error Rate**
```
Alert: sum:ai_pr_reviewer.errors{*}.as_rate() > 5
Window: last 5 minutes
Notify: #devops-alerts
```

**2. Slow Reviews**
```
Alert: avg:ai_pr_reviewer.review.duration{*} > 30
Window: last 15 minutes
Notify: #devops-alerts
```

**3. High Token Cost**
```
Alert: sum:ai_pr_reviewer.tokens.cost{*} > 10
Window: last 1 day
Notify: #finance-alerts
```

**4. Function Errors**
```
Alert: source:azure.functions status:error service:ai-pr-reviewer
Count: > 10
Window: last 5 minutes
Notify: #devops-alerts
```

---

## Log Queries

### Common Queries

**Recent PR reviews:**
```
source:azure.functions service:ai-pr-reviewer @message:"pr_review_started"
```

**Failed reviews:**
```
source:azure.functions service:ai-pr-reviewer status:error
```

**Reviews by repository:**
```
source:azure.functions service:ai-pr-reviewer
| group by @repository
| count
```

**Slow reviews (>30 seconds):**
```
source:azure.functions service:ai-pr-reviewer @duration:>30
```

**Token usage trends:**
```
source:azure.functions service:ai-pr-reviewer @message:"ai_review_completed"
| timeseries sum(@tokens_used) by 1h
```

---

## Alternative Integration Options

### Option A: Azure Integration

For automatic log collection without code changes:

1. In Datadog, go to **Integrations** → **Azure**
2. Click **Add Azure Account**
3. Follow guided setup

**Configure diagnostic settings:**
```bash
az monitor diagnostic-settings create \
  --name send-to-datadog \
  --resource /subscriptions/{sub-id}/resourceGroups/rg-ai-pr-reviewer/providers/Microsoft.Web/sites/func-ai-pr-reviewer \
  --logs '[{"category": "FunctionAppLogs", "enabled": true}]' \
  --metrics '[{"category": "AllMetrics", "enabled": true}]' \
  --event-hub-name datadog-logs \
  --event-hub-rule {event-hub-rule-id}
```

### Option B: Custom Datadog Agent

For maximum control (advanced, typically not needed for Functions):

Install Datadog Agent in Azure Container Instances or AKS and forward logs.

**Not recommended for serverless Functions** - use Extension instead.

---

## Environment Variables

### Required Datadog Settings

```bash
az functionapp config appsettings set \
  --name func-ai-pr-reviewer \
  --resource-group rg-ai-pr-reviewer \
  --settings \
    DD_API_KEY=your-datadog-api-key \
    DD_SITE=datadoghq.com \
    DD_SERVICE=ai-pr-reviewer \
    DD_ENV=production \
    DD_VERSION=2.2.0 \
    DD_LOGS_INJECTION=true \
    DD_TRACE_ENABLED=true \
    DD_PROFILING_ENABLED=false
```

**Get your Datadog API key:**
1. Datadog → **Organization Settings** → **API Keys**
2. Create: "Azure Functions - CodeWarden"
3. Copy the key

---

## Testing

### Verify Integration

**1. Deploy function:**
```bash
func azure functionapp publish func-ai-pr-reviewer --python
```

**2. Trigger a test:**
```bash
curl -X POST https://func-ai-pr-reviewer.azurewebsites.net/api/health
```

**3. Check Datadog Logs:**
```
source:azure.functions service:ai-pr-reviewer
```

**4. Check APM Traces:**
- Go to **APM** → **Traces**
- Filter by `service:ai-pr-reviewer`

---

## Best Practices

### 1. Tag Everything
```python
span.set_tag("env", "production")
span.set_tag("team", "devops")
span.set_tag("repository", repo_name)
span.set_tag("pr_id", pr_id)
```

### 2. Use Structured Logging
```python
logger.info(
    "pr_review_completed",
    extra={
        "pr_id": 123,
        "duration": 15.3,
        "recommendation": "approve",
        "tokens_used": 1200
    }
)
```

### 3. Track Business Metrics
```python
statsd.increment('pr_reviews.approved')
statsd.increment('pr_reviews.rejected')
statsd.histogram('pr_reviews.issues_found', 12)
```

### 4. Set SLOs
- 99% of reviews complete in <30 seconds
- 95% of reviews succeed
- <1% error rate

---

## Troubleshooting

### Logs Not Appearing

**Check:**
1. Is `DD_API_KEY` set correctly?
2. Is `DD_SITE` correct? (datadoghq.com, datadoghq.eu, etc.)
3. Is ddtrace installed? (`pip list | grep ddtrace`)
4. Check Function App logs:
   ```bash
   az webapp log tail --name func-ai-pr-reviewer --resource-group rg-ai-pr-reviewer
   ```

### APM Traces Not Showing

**Solutions:**
1. Ensure `DD_TRACE_ENABLED=true`
2. Verify ddtrace is imported: `from ddtrace import patch_all; patch_all()`
3. Check service name matches: `DD_SERVICE=ai-pr-reviewer`

### High Datadog Costs

**Optimize:**
1. Enable log sampling (send 10% of logs)
2. Filter out debug logs in production
3. Use metrics instead of logs for high-frequency events

---

## Cost Comparison

| Solution | Monthly Cost (100 PRs/month) |
|----------|------------------------------|
| **Application Insights** | $2-5 |
| **Datadog (existing)** | $0 (already paying) |
| **Savings** | **$2-5/month** ✅ |

---

## Summary

**Datadog Integration Benefits:**
- ✅ Use existing infrastructure (no additional cost)
- ✅ Unified monitoring across services
- ✅ Superior UX and dashboards
- ✅ Team already familiar
- ✅ Easy setup (15 minutes)

**Recommended Setup:**
1. Add Datadog extension to Function App
2. Install ddtrace in requirements.txt
3. Create custom dashboard (17 widgets provided)
4. Set up 4 key alerts
5. Monitor and iterate

**Cost Savings:** $2-5/month vs Application Insights

---

## Next Steps

1. ✅ Add `DD_API_KEY` to Function App settings
2. ✅ Update `requirements.txt` with ddtrace
3. ✅ Deploy function
4. ✅ Verify logs in Datadog
5. ✅ Create dashboard
6. ✅ Set up alerts

**You're ready to monitor with Datadog!** 🚀

For reliability monitoring, see `/api/reliability-health` endpoint for:
- Circuit breaker status
- Cache hit rates
- Idempotency statistics
