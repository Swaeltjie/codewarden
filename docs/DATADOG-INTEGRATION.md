# Datadog Integration Guide

## Overview

This guide shows how to integrate your AI PR Reviewer with your existing Datadog infrastructure instead of using Application Insights.

**Benefits:**
- ✅ Use existing Datadog subscription (no additional cost)
- ✅ Unified monitoring across all services
- ✅ Better dashboards and alerting
- ✅ Existing team knowledge
- ✅ No vendor lock-in to Azure monitoring

---

## Integration Options

There are **3 ways** to send logs/metrics from Azure Functions to Datadog:

| Option | Best For | Setup Time | Cost |
|--------|----------|------------|------|
| **1. Azure Integration** | Quick start | 15 min | FREE |
| **2. Datadog Agent** | Full control | 30 min | FREE |
| **3. Datadog Extension** | Easiest | 10 min | FREE |

**Recommendation:** Start with **Option 3 (Extension)** for simplicity.

---

## Option 1: Azure Integration (Recommended for PoC)

### Setup

**Step 1: Enable Datadog Azure Integration**

1. In Datadog, go to **Integrations** → **Azure**
2. Click **Add Azure Account**
3. Follow the guided setup to connect your Azure subscription

**Step 2: Configure Log Collection**

```bash
# Enable diagnostic settings for Function App
az monitor diagnostic-settings create \
  --name send-to-datadog \
  --resource /subscriptions/{subscription-id}/resourceGroups/rg-ai-pr-reviewer/providers/Microsoft.Web/sites/func-ai-pr-reviewer \
  --logs '[
    {
      "category": "FunctionAppLogs",
      "enabled": true
    }
  ]' \
  --metrics '[
    {
      "category": "AllMetrics",
      "enabled": true
    }
  ]' \
  --event-hub-name datadog-logs \
  --event-hub-rule /subscriptions/{subscription-id}/resourceGroups/rg-datadog/providers/Microsoft.EventHub/namespaces/datadog-eventhub/authorizationrules/RootManageSharedAccessKey
```

**Step 3: Verify in Datadog**

```
source:azure.functions service:ai-pr-reviewer
```

---

## Option 2: Datadog Extension (Easiest)

### Setup

**Step 1: Add Datadog Extension to Function App**

```bash
# Add Datadog extension
az functionapp config appsettings set \
  --name func-ai-pr-reviewer \
  --resource-group rg-ai-pr-reviewer \
  --settings \
    DD_API_KEY=your-datadog-api-key \
    DD_SITE=datadoghq.com \
    DD_SERVICE=ai-pr-reviewer \
    DD_ENV=production
```

**Step 2: Install Datadog Python Library**

Add to `requirements.txt`:
```
ddtrace>=2.0.0
```

**Step 3: Enable Datadog Tracing in Code**

Update `function_app.py`:
```python
import logging
from ddtrace import tracer, patch_all

# Enable Datadog tracing
patch_all()

# Configure logging to send to Datadog
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)
```

**Step 4: Deploy**

```bash
func azure functionapp publish func-ai-pr-reviewer --python
```

---

## Option 3: Custom Datadog Agent (Advanced)

For maximum control, install Datadog Agent in Azure Container Instances or AKS and forward logs.

**Not recommended for serverless Functions** - use Extension instead.

---

## Structured Logging for Datadog

### Update Your Logging Code

Replace `structlog` Application Insights configuration with Datadog-friendly logging:

```python
# src/utils/logging.py
import logging
import json
from datetime import datetime

class DatadogFormatter(logging.Formatter):
    """Format logs for Datadog ingestion."""
    
    def format(self, record):
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": "ai-pr-reviewer",
            "ddsource": "python",
        }
        
        # Add extra fields
        if hasattr(record, 'pr_id'):
            log_data['pr_id'] = record.pr_id
        if hasattr(record, 'repository'):
            log_data['repository'] = record.repository
        if hasattr(record, 'duration'):
            log_data['duration'] = record.duration
            
        return json.dumps(log_data)


def setup_logging(log_level: str = "INFO"):
    """Configure logging for Datadog."""
    
    # Create logger
    logger = logging.getLogger()
    logger.setLevel(log_level)
    
    # Create handler
    handler = logging.StreamHandler()
    handler.setFormatter(DatadogFormatter())
    
    # Add handler to logger
    logger.addHandler(handler)
    
    return logger


# Usage in your code:
logger = logging.getLogger(__name__)

logger.info(
    "PR review started",
    extra={
        "pr_id": 123,
        "repository": "terraform-repo",
        "file_count": 5
    }
)
```

### Better: Use ddtrace for Auto-Instrumentation

```python
# src/utils/logging.py
from ddtrace import tracer
import logging

logger = logging.getLogger(__name__)

@tracer.wrap(service="ai-pr-reviewer", resource="review_pr")
def review_pr(pr_id: int):
    """Review a PR with automatic Datadog tracing."""
    
    span = tracer.current_span()
    span.set_tag("pr_id", pr_id)
    span.set_tag("env", "production")
    
    logger.info(f"Reviewing PR {pr_id}")
    
    # Your code here
    
    span.set_metric("review_duration", 15.3)
    span.set_tag("recommendation", "approve")
```

---

## Custom Metrics

### Send Custom Metrics to Datadog

```python
# src/utils/metrics.py
from datadog import initialize, statsd
import os

# Initialize Datadog
initialize(
    api_key=os.getenv('DD_API_KEY'),
    app_key=os.getenv('DD_APP_KEY')
)

class MetricsClient:
    """Send custom metrics to Datadog."""
    
    @staticmethod
    def record_pr_review(duration: float, recommendation: str, file_count: int):
        """Record PR review metrics."""
        
        # Duration histogram
        statsd.histogram(
            'ai_pr_reviewer.review.duration',
            duration,
            tags=[f'recommendation:{recommendation}']
        )
        
        # File count gauge
        statsd.gauge(
            'ai_pr_reviewer.review.file_count',
            file_count
        )
        
        # Review counter
        statsd.increment(
            'ai_pr_reviewer.review.count',
            tags=[f'recommendation:{recommendation}']
        )
    
    @staticmethod
    def record_token_usage(tokens: int, cost: float):
        """Record AI token usage and cost."""
        
        statsd.histogram('ai_pr_reviewer.tokens.used', tokens)
        statsd.histogram('ai_pr_reviewer.tokens.cost', cost)


# Usage:
metrics = MetricsClient()
metrics.record_pr_review(duration=15.3, recommendation="approve", file_count=5)
metrics.record_token_usage(tokens=1200, cost=0.012)
```

---

## Datadog Dashboards

### Create Custom Dashboard

**Template Dashboard JSON:**

```json
{
  "title": "AI PR Reviewer - Performance",
  "widgets": [
    {
      "definition": {
        "title": "PR Review Success Rate",
        "type": "query_value",
        "requests": [
          {
            "q": "sum:ai_pr_reviewer.review.count{recommendation:approve}.as_count() / sum:ai_pr_reviewer.review.count{*}.as_count() * 100"
          }
        ]
      }
    },
    {
      "definition": {
        "title": "Average Review Duration",
        "type": "timeseries",
        "requests": [
          {
            "q": "avg:ai_pr_reviewer.review.duration{*}",
            "display_type": "line"
          }
        ]
      }
    },
    {
      "definition": {
        "title": "Token Usage & Cost",
        "type": "timeseries",
        "requests": [
          {
            "q": "sum:ai_pr_reviewer.tokens.used{*}",
            "display_type": "bars"
          },
          {
            "q": "sum:ai_pr_reviewer.tokens.cost{*}",
            "display_type": "line"
          }
        ]
      }
    },
    {
      "definition": {
        "title": "Error Rate",
        "type": "query_value",
        "requests": [
          {
            "q": "sum:ai_pr_reviewer.errors{*}.as_count() / sum:ai_pr_reviewer.review.count{*}.as_count() * 100"
          }
        ]
      }
    }
  ]
}
```

**Import via Datadog UI:**
1. Go to **Dashboards** → **New Dashboard**
2. Click **Import Dashboard JSON**
3. Paste the JSON above
4. Click **Import**

---

## Alerts

### Recommended Alerts

**1. High Error Rate**
```
Alert when: sum:ai_pr_reviewer.errors{*}.as_rate() > 5
Time window: last 5 minutes
Notify: #devops-alerts
```

**2. Slow Reviews**
```
Alert when: avg:ai_pr_reviewer.review.duration{*} > 30
Time window: last 15 minutes
Notify: #devops-alerts
```

**3. High Token Cost**
```
Alert when: sum:ai_pr_reviewer.tokens.cost{*} > 10
Time window: last 1 day
Notify: #finance-alerts
```

**4. Function Errors**
```
Alert when: source:azure.functions status:error service:ai-pr-reviewer
Count: > 10
Time window: last 5 minutes
Notify: #devops-alerts
```

---

## Log Queries (Examples)

### Datadog Log Explorer Queries

**Recent PR reviews:**
```
source:azure.functions service:ai-pr-reviewer @message:"PR review started"
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
source:azure.functions service:ai-pr-reviewer @message:"AI review completed"
| timeseries sum(@tokens_used) by 1h
```

---

## APM (Application Performance Monitoring)

### Enable Datadog APM

**Update requirements.txt:**
```
ddtrace>=2.0.0
```

**Wrap your functions with tracing:**

```python
from ddtrace import tracer

@app.route(route="pr-webhook", methods=["POST"])
@tracer.wrap(service="ai-pr-reviewer", resource="pr-webhook")
async def pr_webhook(req: func.HttpRequest) -> func.HttpResponse:
    span = tracer.current_span()
    
    # Parse request
    pr_event = parse_pr_event(req)
    span.set_tag("pr_id", pr_event.pr_id)
    span.set_tag("repository", pr_event.repository)
    
    # Process PR
    with tracer.trace("fetch_pr_details"):
        pr_details = await fetch_pr_details(pr_event)
    
    with tracer.trace("ai_review"):
        review_result = await ai_client.review(pr_details)
        span.set_metric("tokens_used", review_result.tokens)
    
    with tracer.trace("post_results"):
        await post_results_to_devops(review_result)
    
    return func.HttpResponse(status_code=202)
```

**View in Datadog:**
- Go to **APM** → **Services** → **ai-pr-reviewer**
- See trace waterfall for each PR review
- Identify bottlenecks (usually AI API calls)

---

## Environment Variables

### Required Datadog Settings

Add to your Function App configuration:

```bash
az functionapp config appsettings set \
  --name func-ai-pr-reviewer \
  --resource-group rg-ai-pr-reviewer \
  --settings \
    DD_API_KEY=your-datadog-api-key \
    DD_SITE=datadoghq.com \
    DD_SERVICE=ai-pr-reviewer \
    DD_ENV=production \
    DD_VERSION=1.0.0 \
    DD_LOGS_INJECTION=true \
    DD_TRACE_ENABLED=true \
    DD_PROFILING_ENABLED=false
```

**Get your Datadog API key:**
1. Go to Datadog → **Organization Settings** → **API Keys**
2. Create new API key: "Azure Functions - AI PR Reviewer"
3. Copy the key

---

## Testing

### Verify Datadog Integration

**1. Deploy function:**
```bash
func azure functionapp publish func-ai-pr-reviewer --python
```

**2. Trigger a test:**
```bash
curl -X POST https://func-ai-pr-reviewer.azurewebsites.net/api/health
```

**3. Check Datadog:**
```
# In Datadog Log Explorer
source:azure.functions service:ai-pr-reviewer
```

**4. Check APM:**
- Go to **APM** → **Traces**
- Filter by `service:ai-pr-reviewer`
- You should see traces

---

## Cost Comparison

| Solution | Monthly Cost (100 PRs/month) |
|----------|------------------------------|
| **Application Insights** | $2-5 |
| **Datadog (existing)** | $0 (already paying) |
| **Savings** | **$2-5/month** ✅ |

---

## Troubleshooting

### Logs Not Appearing in Datadog

**Check:**
1. Is `DD_API_KEY` set correctly?
2. Is `DD_SITE` correct? (datadoghq.com, datadoghq.eu, etc.)
3. Is ddtrace installed? (`pip list | grep ddtrace`)
4. Check Function App logs for errors:
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
    "PR review completed",
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

### 4. Set SLOs (Service Level Objectives)
- 99% of reviews complete in <30 seconds
- 95% of reviews succeed
- <1% error rate

---

## Summary

**Datadog Integration:**
- ✅ Use existing infrastructure (no additional cost)
- ✅ Unified monitoring
- ✅ Better dashboards than App Insights
- ✅ Easy setup with Azure extension

**Recommended Setup:**
1. Add Datadog extension to Function App (10 min)
2. Install ddtrace in requirements.txt
3. Add logging with extra fields
4. Create custom dashboard
5. Set up alerts

**Cost Savings: $2-5/month** vs Application Insights

---

## Next Steps

1. ✅ Add DD_API_KEY to Function App settings
2. ✅ Update requirements.txt with ddtrace
3. ✅ Deploy function
4. ✅ Verify logs in Datadog
5. ✅ Create dashboard
6. ✅ Set up alerts

**You're ready to monitor with Datadog!** 🚀
