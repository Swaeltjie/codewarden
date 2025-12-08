# Architecture & Storage Decisions

## Architecture Overview

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                          Azure DevOps                           │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐          │
│  │  Developer  │───▶│    Pull    │───▶│   Service   │          │
│  │  Creates PR │    │   Request   │    │    Hook     │          │
│  └─────────────┘    └─────────────┘    └──────┬──────┘          │
└───────────────────────────────────────────────┼─────────────────┘
                                                │
                   Webhook (HTTP POST)          │
                   PR Event JSON                │
                                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Azure Functions (Python 3.12)                  │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                 HTTP Trigger: pr_webhook                  │  │
│  │  • Validate webhook secret                                │  │
│  │  • Parse PR event                                         │  │
│  │  • Return 202 Accepted (async processing)                 │  │
│  └────────────────────────┬──────────────────────────────────┘  │
│                           ▼                                     │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │          PR Review Orchestrator (pr_webhook.py)           │  │
│  │                                                           │  │
│  │  Step 1: Fetch PR Details                                 │  │
│  │    ├─ Get changed files from Azure DevOps API             │  │
│  │    ├─ Download git diffs for each file                    │  │
│  │    └─ Classify file types (Terraform, Ansible, etc.)      │  │
│  │                                                           │  │
│  │  Step 2: Parse Diffs (Diff-Only Analysis)                 │  │
│  │    ├─ Extract only changed lines (+ removed, added)       │  │
│  │    ├─ Include 3 lines context before/after                │  │
│  │    └─ Calculate token savings (50-85%)                    │  │
│  │                                                           │  │
│  │  Step 3: Determine Review Strategy                        │  │
│  │    ├─ Small PR (≤5 files) → Single-pass review            │  │
│  │    ├─ Medium PR (6-15) → Chunked review                   │  │
│  │    └─ Large PR (>15) → Hierarchical review                │  │
│  │                                                           │  │
│  │  Step 4: Get Learning Context                             │  │
│  │    ├─ Load feedback from Table Storage                    │  │
│  │    ├─ Identify high/low value checks                      │  │
│  │    └─ Apply team-specific patterns                        │  │
│  │                                                           │  │
│  │  Step 5: AI Review                                        │  │
│  │    ├─ Build technology-specific prompt                    │  │
│  │    ├─ Call OpenAI API (with retry logic)                  │  │
│  │    └─ Parse structured JSON response                      │  │
│  │                                                           │  │
│  │  Step 6: Post Results                                     │  │
│  │    ├─ Summary comment to PR                               │  │
│  │    └─ Inline comments for critical issues                 │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │     Timer Trigger: feedback_collector (Hourly)            │  │
│  │  • Monitor PR threads for reactions (thumbs up/down)      │  │
│  │  • Track resolved/won't fix status                        │  │
│  │  • Store feedback in Table Storage                        │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │    Timer Trigger: pattern_detector (Daily 2 AM)           │  │
│  │  • Analyze historical reviews from Table Storage          │  │
│  │  • Detect recurring issues                                │  │
│  │  • Identify problematic files                             │  │
│  │  • Generate monthly reports                               │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
        │                    │                    │
        ▼                    ▼                    ▼
┌────────────────┐  ┌────────────────┐  ┌────────────────┐
│  Azure Key     │  │    OpenAI      │  │  Azure Table   │
│    Vault       │  │      API       │  │    Storage     │
│                │  │                │  │                │
│ • OpenAI Key   │  │ • GPT-4 Review │  │ • Feedback     │
│ • Webhook      │  │ • Embeddings   │  │ • History      │
│   Secret       │  │                │  │ • Patterns     │
│                │  │                │  │                │
└────────────────┘  └────────────────┘  └────────────────┘
```

---

## Review Strategy: Adaptive 3-Tier System

### How It Works

The system automatically chooses the best review strategy based on PR size:

```python
def determine_strategy(files: List[FileChange]) -> ReviewStrategy:
    total_tokens = sum(estimate_tokens(f.changed_sections) for f in files)

    if len(files) <= 5 and total_tokens <= 10_000:
        return ReviewStrategy.SINGLE_PASS
    elif len(files) <= 15 and total_tokens <= 40_000:
        return ReviewStrategy.CHUNKED
    else:
        return ReviewStrategy.HIERARCHICAL
```

### Strategy Details

#### Tier 1: Single-Pass Review (Small PRs)
**When:** ≤5 files, ≤10K tokens

```
┌────────────────────────────────────────┐
│  All changed sections in one prompt    │
│                                        │
│  File 1: main.tf (15 changed lines)    │
│  File 2: vars.tf (8 changed lines)     │
│  File 3: outputs.tf (3 changed lines)  │
│                                        │
│          ↓ Single AI Call ↓            │
│                                        │
│  Comprehensive review considering      │
│  all files together                    │
└────────────────────────────────────────┘
```

**Benefits:**
- Fastest (5-8 seconds)
- Most contextually aware
- Single coherent review

#### Tier 2: Chunked Review (Medium PRs)
**When:** 6-15 files, 10K-40K tokens

```
┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
│   Group 1           │  │   Group 2           │  │   Group 3           │
│ ┌─────────────────┐ │  │ ┌─────────────────┐ │  │ ┌─────────────────┐ │
│ │ main.tf         │ │  │ │ network.tf      │ │  │ │ security.tf     │ │
│ │ variables.tf    │ │  │ │ subnets.tf      │ │  │ │ iam.tf          │ │
│ │ outputs.tf      │ │  │ │ firewall.tf     │ │  │ │ kms.tf          │ │
│ └─────────────────┘ │  │ └─────────────────┘ │  │ └─────────────────┘ │
│        ↓            │  │        ↓            │  │        ↓            │
│   AI Review 1       │  │   AI Review 2       │  │   AI Review 3       │
└─────────────────────┘  └─────────────────────┘  └─────────────────────┘
           │                       │                       │
           └───────────────────────┴───────────────────────┘
                                   ↓
                         Aggregate Results
```

**Benefits:**
- Maintains logical grouping
- Parallel processing possible
- Better than individual file reviews

#### Tier 3: Hierarchical Review (Large PRs)
**When:** >15 files, >40K tokens

```
Phase 1: Individual File Reviews (Parallel)
┌───────┐  ┌───────┐  ┌───────┐  ┌───────┐
│File 1 │  │File 2 │  │File 3 │  │...    │
│Review │  │Review │  │Review │  │File N │
└───┬───┘  └───┬───┘  └───┬───┘  └───┬───┘
    │          │          │          │
    └──────────┴──────────┴──────────┘
                    ↓
Phase 2: Cross-File Analysis (Only Critical Issues)
┌─────────────────────────────────────┐
│ Analyze dependencies between files  │
│ with critical/high severity issues  │
└─────────────────────────────────────┘
                    ↓
Phase 3: Aggregate Summary
┌─────────────────────────────────────┐
│ • Consolidated findings             │
│ • Prioritized by severity           │
│ • Human decision summary            │
└─────────────────────────────────────┘
```

**Benefits:**
- Scales to any PR size
- Detailed per-file analysis
- Identifies cross-file issues

---

## Storage Architecture: Why Table Storage?

### The Question: Cosmos DB vs Table Storage vs SQL?

We evaluated three options for storing feedback and historical data:

| Criteria | Table Storage | Cosmos DB | Azure SQL |
|----------|---------------|-----------|-----------|
| **Cost (1K entries/month)** | $0.10 ✅ | $1-2 | $5-15 |
| **Performance** | Sub-100ms ✅ | Sub-10ms | 10-50ms |
| **Scalability** | Auto ✅ | Auto ✅ | Manual |
| **Query Complexity** | Simple ✅ | Complex | Complex |
| **Global Distribution** | No | Yes | No |
| **Setup Complexity** | Low ✅ | Medium | Medium |
| **Best For** | Key-value ✅ | Global apps | Relational data |

### Decision: Azure Table Storage ✅

**Why Table Storage Wins:**

1. **Cost-Effective** (10-20x cheaper)
   - $0.045/GB/month
   - No per-request charges (unlike Cosmos DB)
   - Included with Storage Account

2. **Perfect Access Patterns**
   ```python
   # Our queries are simple key-value lookups

   # Get specific feedback
   feedback = table_client.get_entity(
       partition_key="terraform-repo",
       row_key="feedback_12345"
   )

   # Get recent feedback for repository
   recent = table_client.query_entities(
       "PartitionKey eq 'terraform-repo' and Timestamp gt datetime'2025-11-01'"
   )
   ```

3. **Fast Enough**
   - Sub-100ms queries (we don't need sub-10ms)
   - Our bottleneck is AI API (5-20 seconds), not storage

4. **Simple & Reliable**
   - NoSQL key-value store
   - 99.9% SLA
   - No complex configuration

5. **Already There**
   - Same Storage Account used by Azure Functions
   - No additional resource to manage

### Data Models

#### Feedback Table

```python
# PartitionKey: repository_name (for efficient queries)
# RowKey: feedback_id (unique identifier)

{
  "PartitionKey": "terraform-prod-repo",
  "RowKey": "fb_67890",
  "Timestamp": "2025-11-30T12:34:56Z",

  # Feedback details
  "pr_id": "123",
  "suggestion_id": "sg_456",
  "issue_type": "PublicEndpoint",
  "severity": "High",
  "feedback_type": "Accepted",  # Accepted, Rejected, Ignored
  "developer_id": "user@company.com",
  "file_type": "Terraform",

  # Metrics
  "response_time_hours": 2.5
}
```

#### Review History Table

```python
# PartitionKey: repository_name
# RowKey: pr_id

{
  "PartitionKey": "terraform-prod-repo",
  "RowKey": "pr_123",
  "Timestamp": "2025-11-30T12:00:00Z",

  # Review metadata
  "author_email": "dev@company.com",
  "files_reviewed": 8,
  "file_types": "Terraform,Ansible",

  # Results
  "issues_found": 12,
  "issues_critical": 2,
  "issues_high": 5,
  "issues_medium": 3,
  "issues_low": 2,

  # Outcomes
  "issues_fixed": 10,
  "issues_ignored": 2,
  "recommendation": "request_changes",

  # Performance
  "duration_seconds": 18.5,
  "tokens_used": 1200,
  "strategy_used": "CHUNKED"
}
```

### When to Upgrade to Cosmos DB

Cosmos DB makes sense if you need:

1. **Global Distribution**
   - Multiple regions (US, Europe, Asia)
   - Multi-region writes
   - Geo-replication

2. **Complex Queries**
   - GraphQL API
   - SQL-like queries with JOINs
   - Aggregations across partitions
   - Full-text search

3. **Massive Scale**
   - Millions of requests per day
   - Auto-scaling to thousands of RU/s
   - Guaranteed low latency (< 10ms)

4. **Multi-Model Support**
   - Documents (MongoDB API)
   - Graphs (Gremlin)
   - Key-value (Table API)
   - Column-family (Cassandra)

### Migration Path

If you outgrow Table Storage, migrating to Cosmos DB is straightforward:

```bash
# Azure provides built-in migration tools
az cosmosdb table migrate \
  --source-account-name $STORAGE_ACCOUNT \
  --dest-account-name $COSMOS_ACCOUNT \
  --table-name feedback

# Or use Azure Data Factory for complex migrations
```

---

## Technology Choices Summary

### Core Stack

| Component | Choice | Alternatives Considered | Why This One |
|-----------|--------|------------------------|--------------|
| **Runtime** | Azure Functions Python | C#, Java, Node.js | Best AI library support |
| **Language** | Python 3.12 | C# .NET 8 | 2x faster development, better AI ecosystem |
| **AI API** | OpenAI GPT-4 | Azure AI, Anthropic Claude | Most mature, best results |
| **Storage** | Azure Table Storage | Cosmos DB, Azure SQL | 10-20x cheaper, perfect for use case |
| **Secrets** | Azure Key Vault | Environment vars | Enterprise security standard |
| **Logging** | Application Insights | Custom logging | Native Azure integration |
| **DevOps** | Azure DevOps API | GitHub API, GitLab | Project requirement |

### Cost Impact of Choices

**Monthly Cost Breakdown (100 PRs/month):**

| Choice | Cost |
|--------|------|
| Azure Functions (Consumption) | $0.10 |
| Table Storage (not Cosmos DB) | $0.10 ✅ Saved $1-2 |
| Diff-Only Analysis (not full files) | $8 ✅ Saved $42 |
| Python (vs C# Premium plan) | $0 ✅ Same cost |
| **Total** | **$12-15/month** |

**Total Savings from Smart Choices:** ~$43/month (78% reduction)

---

## Performance Characteristics

### End-to-End Latency

```
Total Review Time: 5-30 seconds
├─ Webhook processing: 50ms (Python overhead)
├─ Fetch PR details: 500ms (Azure DevOps API)
├─ Parse diffs: 100ms (Python diff parser)
├─ Determine strategy: 10ms
├─ Load learning context: 50ms (Table Storage)
├─ AI review: 5-20 seconds ◄── 90% of time
├─ Post results: 500ms (Azure DevOps API)
└─ Store history: 50ms (Table Storage)

Key Insight: Python's 50ms overhead is 0.25% of total time
```

### Scalability

**Current Architecture Handles:**
- 100 PRs/month: No problem
- 1,000 PRs/month: No problem (Consumption plan auto-scales)
- 10,000 PRs/month: Need Premium plan ($150/month) but still works

**Bottlenecks (in order):**
1. OpenAI API rate limits (60 requests/minute)
2. Azure DevOps API rate limits (200 requests/5 minutes)
3. Azure Functions concurrency (100 concurrent on Consumption)
4. Table Storage throughput (20,000 ops/second - not a concern)

---

## Security Architecture

CodeWarden uses a **zero-credential** architecture powered by Azure Managed Identity and Azure Key Vault for maximum security.

### Authentication Methods

| Service | Method | Access Control |
|---------|--------|----------------|
| **Azure Key Vault** | Managed Identity | RBAC (Key Vault Secrets User) |
| **Azure Table Storage** | Managed Identity | RBAC (Storage Table Data Contributor) |
| **Azure DevOps API** | Managed Identity | Azure AD + Project Permissions |
| **OpenAI / Azure OpenAI** | API Key | Stored in Key Vault |

### Security Layers

```
Layer 1: Network
├─ HTTPS only (enforced by Azure)
├─ Function URL with key required
└─ Webhook secret validation (HMAC, constant-time comparison)

Layer 2: Identity & Access
├─ Managed Identity (no credentials in code)
├─ Azure RBAC (least privilege)
├─ Key Vault secrets access
└─ Azure AD audit logs

Layer 3: Data Protection
├─ Secrets in Key Vault only
├─ Encrypted at rest (Storage, Key Vault)
├─ Encrypted in transit (TLS 1.2+)
└─ PR diffs transient (memory only)

Layer 4: Application Security
├─ No hardcoded secrets
├─ Input validation (Pydantic)
├─ Path traversal prevention
├─ Payload size limits (1MB max)
└─ Security scanning (Bandit)

Layer 5: Monitoring
├─ Structured logging (no secrets logged)
├─ Azure AD sign-in logs
├─ Key Vault audit logs
└─ Anomaly detection
```

### Secrets Flow

```
Developer pushes PR
        ↓
Webhook → Function (validates secret from header)
        ↓
Function needs OpenAI key
        ↓
Function uses Managed Identity → Key Vault → Gets secret
        ↓
Function calls OpenAI API
        ↓
Results posted to DevOps (uses Managed Identity Azure AD token)
```

**Zero secrets in code or environment variables** ✅

### Threat Mitigations

| Threat | Mitigations |
|--------|-------------|
| **Credential Theft** | No credentials in code; MI cannot be extracted; Key Vault only |
| **Webhook Injection** | Secret validation (HMAC); payload limits; JSON depth validation |
| **Path Traversal** | Path sanitization; reject `../`; null byte checking |
| **Secrets in Logs** | Structured logging with field filtering; sanitized output |
| **API Abuse** | Webhook auth required; rate limiting; cost monitoring |
| **AI Code Injection** | JSON-only responses; schema validation; no code execution |

### Security Checklist

**Pre-Deployment:**
- [ ] System-assigned Managed Identity enabled
- [ ] Key Vault RBAC roles configured
- [ ] Table Storage RBAC roles assigned
- [ ] Secrets stored in Key Vault (not env vars)
- [ ] HTTPS enforced
- [ ] Function-level auth on endpoints

**Ongoing:**
- [ ] Rotate OpenAI API key (30 days)
- [ ] Review RBAC assignments monthly
- [ ] Update dependencies quarterly
- [ ] Monitor for authentication failures

---

## Monitoring & Observability

### Key Metrics

```kusto
// Application Insights Query

// PR Review Success Rate
requests
| where name == "pr-webhook"
| summarize
    SuccessRate = countif(resultCode == 200) * 100.0 / count(),
    AvgDuration = avg(duration)
  by bin(timestamp, 1h)

// Token Usage & Cost
customMetrics
| where name == "ai_tokens_used"
| extend cost = value * 0.00001  // $0.01 per 1K tokens
| summarize
    TotalTokens = sum(value),
    TotalCost = sum(cost)
  by bin(timestamp, 1d)

// Feedback Acceptance Rate
customEvents
| where name == "feedback_recorded"
| extend feedbackType = tostring(customDimensions.feedback_type)
| summarize AcceptanceRate = countif(feedbackType == "Accepted") * 100.0 / count()
  by repository = tostring(customDimensions.repository)
```

### Alerts

- Failed reviews (>5 in 5 minutes)
- OpenAI API errors (>10 in 1 hour)
- Table Storage throttling (>100 in 5 minutes)
- Cost threshold exceeded (>$20/day)

---

## Future Architecture Considerations

### When to Evolve

**Trigger Points:**
1. **>1,000 PRs/month** → Move to Premium plan
2. **Global team** → Consider Cosmos DB for multi-region
3. **Complex queries needed** → Upgrade to Cosmos DB or SQL
4. **Custom ML models** → Add Azure ML for team-specific models
5. **Enterprise scale** → Consider AKS deployment

### Evolution Path

```
Phase 1 & 2 (✅ CURRENT - v2.1.0):
Azure Functions + Table Storage + OpenAI
+ Feedback tracking (production)
+ Pattern detection (production)
+ Learning system (production)
+ Repository health scoring
Cost: $12-15/month
Scale: 500 PRs/month

Phase 3 (Next milestone - 6-12 months):
Azure Functions Premium + Table Storage + Custom models
+ Multi-model support (Claude, Gemini)
+ Advanced caching layer
+ Custom rule engine
Cost: $150-200/month
Scale: 5,000 PRs/month

Phase 4 (Enterprise - 1-2 years):
AKS + Cosmos DB + Multi-region
+ Global deployment
+ Custom ML models
+ Enterprise SLAs
Cost: $500-1,000/month
Scale: 50,000+ PRs/month
```

---

## Conclusion

**Architecture Decisions Summary:**

✅ **Python over C#:** Better AI ecosystem, 2x faster development
✅ **Table Storage over Cosmos DB:** 10-20x cheaper, perfect fit
✅ **Diff-Only over Full Files:** 88% token savings
✅ **Consumption Plan over Premium:** Pay per use, scales automatically
✅ **Managed Identity over Keys:** Zero secrets in code

**Total Result:** Enterprise-grade solution at $12-15/month 🎯

The architecture is designed to:
- Start cheap (PoC)
- Scale easily (auto-scaling)
- Evolve gradually (clear upgrade paths)
- Stay secure (defense in depth)
- Remain maintainable (clean code, good practices)

**Ready for production!** 🚀
