# Azure Resources Inventory

## Complete Resource List

Here are ALL Azure resources you'll create for the AI PR Reviewer solution:

### Resource Summary

| # | Resource Type | Resource Name | Purpose | Monthly Cost |
|---|--------------|---------------|---------|--------------|
| 1 | Resource Group | rg-ai-pr-reviewer | Logical container for all resources | FREE |
| 2 | Storage Account | staiprreviewer | Functions runtime + Table Storage | $1.00 |
| 3 | Function App | func-ai-pr-reviewer | Main application (Python 3.12) | $0.10-150* |
| 4 | App Service Plan | ASP-Consumption | Hosting plan for Functions | FREE* |
| 5 | Key Vault | kv-ai-pr-reviewer | Secure secrets storage | $0.50 |
| | | | **Total (PoC)** | **$1.60** |
| | | | **Total (Production)** | **$151.60** |

*Consumption plan is pay-per-execution ($0.10/month for 100 PRs). Production uses Premium plan ($150/month).

**Note:** This architecture uses Datadog for monitoring (your existing infrastructure) - no Application Insights required.

---

## Detailed Resource Breakdown

### 1. Resource Group

**Name:** `rg-ai-pr-reviewer`  
**Type:** Container  
**Purpose:** Logical grouping of all resources  
**Cost:** FREE  

**Why:** Azure best practice for organizing related resources. Makes it easy to:
- View all resources in one place
- Apply consistent tags and policies
- Delete everything at once if needed
- Set up cost alerts

**CLI Command:**
```bash
az group create \
  --name rg-ai-pr-reviewer \
  --location eastus
```

---

### 2. Storage Account ⭐ CRITICAL

**Name:** `staiprreviewer` (must be globally unique)  
**Type:** StorageV2 (General Purpose v2)  
**SKU:** Standard_LRS (Locally Redundant Storage)  
**Cost:** ~$1/month  

**Purpose (Dual Role):**

**Role A: Azure Functions Runtime Storage**
- Stores function code and binaries
- Function execution state
- Internal coordination files
- Required for Functions to operate

**Role B: Data Storage (Table Storage)**
- `feedback` table - Stores developer feedback
- `reviewhistory` table - Stores PR review history
- Used by Phase 2 features (learning system)

**Contains:**
```
staiprreviewer/
├── Blob Storage
│   └── azure-webjobs-* (Functions runtime)
├── Table Storage ⭐ OUR DATA
│   ├── feedback (Phase 2)
│   └── reviewhistory (Phase 2)
├── Queue Storage
│   └── (unused for now, available for future async processing)
└── File Storage
    └── (unused)
```

**CLI Commands:**
```bash
# Create Storage Account
az storage account create \
  --name staiprreviewer \
  --resource-group rg-ai-pr-reviewer \
  --location eastus \
  --sku Standard_LRS \
  --kind StorageV2

# Create Table Storage tables (Phase 2)
az storage table create \
  --name feedback \
  --account-name staiprreviewer

az storage table create \
  --name reviewhistory \
  --account-name staiprreviewer
```

**Cost Breakdown:**
- Base storage: $0.0184/GB/month
- Table operations: $0.0036 per 10,000 transactions
- For 100 PRs/month with 1,000 feedback entries: ~$1/month

---

### 3. Azure Functions App ⭐ MAIN APPLICATION

**Name:** `func-ai-pr-reviewer`
**Runtime:** Python 3.12
**Runtime Version:** Azure Functions v4
**OS:** Linux
**Cost:** $0.10/month (PoC) or $150/month (Production)  

**Purpose:** 
The main application that runs your Python code. Contains:

**Functions (Triggers):**
1. **pr-webhook** (HTTP Trigger)
   - Receives webhooks from Azure DevOps
   - Processes PR events
   - Returns 202 Accepted

2. **feedback-collector** (Timer Trigger)
   - Runs hourly (cron: `0 0 * * * *`)
   - Collects feedback from PR threads
   - Stores in Table Storage

3. **pattern-detector** (Timer Trigger)
   - Runs daily at 2 AM (cron: `0 0 2 * * *`)
   - Analyzes historical patterns
   - Generates reports

4. **health** (HTTP Trigger)
   - Health check endpoint
   - Returns 200 if healthy
   - No authentication required

**Configuration:**
```json
{
  "version": "2.0",
  "functionTimeout": "00:10:00",
  "extensions": {
    "http": {
      "maxConcurrentRequests": 100
    }
  }
}
```

**CLI Commands:**
```bash
# Create Function App
az functionapp create \
  --resource-group rg-ai-pr-reviewer \
  --consumption-plan-location eastus \
  --runtime python \
  --runtime-version 3.11 \
  --functions-version 4 \
  --name func-ai-pr-reviewer \
  --storage-account staiprreviewer \
  --os-type Linux

# Deploy code
func azure functionapp publish func-ai-pr-reviewer --python
```

**Endpoints:**
```
https://func-ai-pr-reviewer.azurewebsites.net/api/pr-webhook
https://func-ai-pr-reviewer.azurewebsites.net/api/health
```

---

### 4. App Service Plan

**Name:** Automatically created (ASP-{region}-{random})  
**Type:** Consumption (PoC) or Premium EP1 (Production)  
**Cost:** FREE (Consumption) or $150/month (Premium)  

**Purpose:** 
Defines the hosting environment for your Function App.

**Consumption Plan (PoC/Dev):**
- ✅ Pay per execution (first 1M executions FREE)
- ✅ Auto-scales (0 to 200 instances)
- ✅ No idle costs
- ⚠️ Cold start (~2.5 seconds)
- ⚠️ 10-minute max execution time

**Premium Plan (Production):**
- ✅ No cold starts (always-warm instances)
- ✅ VNet integration possible
- ✅ Unlimited execution time
- ⚠️ Fixed cost ($150/month)

**Pricing:**
```
Consumption:
- First 1M executions: FREE
- After: $0.20 per million
- Memory: $0.000016/GB-s
- 100 PRs/month = ~$0.10

Premium EP1:
- 1 instance: $150/month
- Memory: 3.5 GB
- vCPU: 1
```

**Note:** App Service Plan is automatically created when you create the Function App. You don't create it separately for Consumption plan.

---

### 5. Azure Key Vault ⭐ SECURITY

**Name:** `kv-ai-pr-reviewer`  
**SKU:** Standard  
**Cost:** ~$0.50/month  

**Purpose:** 
Securely stores ALL secrets (no secrets in code or environment variables)

**Secrets Stored:**
```
kv-ai-pr-reviewer/
├── OPENAI-API-KEY
│   └── OpenAI API key for GPT-4 reviews
└── WEBHOOK-SECRET
    └── Shared secret for validating webhooks
```

**Access Method:**
- Function App uses **Managed Identity** (no credentials needed!)
- Key Vault access policy grants Function App read permissions
- Secrets loaded at runtime via `SecretClient`

**Security:**
```python
# In your code (no credentials!)
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

credential = DefaultAzureCredential()  # Uses managed identity
client = SecretClient(vault_url=keyvault_url, credential=credential)
secret = client.get_secret("OPENAI-API-KEY")
```

**CLI Commands:**
```bash
# Create Key Vault
az keyvault create \
  --name kv-ai-pr-reviewer \
  --resource-group rg-ai-pr-reviewer \
  --location eastus

# Grant Function App access
PRINCIPAL_ID=$(az functionapp identity show \
  --name func-ai-pr-reviewer \
  --resource-group rg-ai-pr-reviewer \
  --query principalId -o tsv)

az keyvault set-policy \
  --name kv-ai-pr-reviewer \
  --object-id $PRINCIPAL_ID \
  --secret-permissions get list

# Store secrets
az keyvault secret set \
  --vault-name kv-ai-pr-reviewer \
  --name "OPENAI-API-KEY" \
  --value "sk-..."
```

**Cost Breakdown:**
- Secret operations: $0.03 per 10,000 transactions
- Secrets stored: 2 secrets (FREE for <25,000 secrets)
- Total: ~$0.50/month

---

### 6. Monitoring: Datadog (Your Existing Infrastructure)

**Not an Azure resource** - Using your existing Datadog subscription
**Cost:** $0 (already paying for Datadog)

**Purpose:**
Comprehensive monitoring, logging, and analytics using your existing Datadog infrastructure

**Integration Methods:**
1. **Datadog Azure Integration** - Automatic log collection
2. **ddtrace library** - Application Performance Monitoring (APM) and logging
3. **datadog statsd** - Custom metrics

**See:** [Datadog Integration Guide](DATADOG-INTEGRATION.md) for complete setup

**Capabilities:**

**1. Logging:**
```python
logger.info(
    "PR review started",
    extra={
        "pr_id": 123,
        "repository": "terraform-repo"
    }
)
# Automatically sent to Datadog
```

**2. Metrics:**
```python
from datadog import statsd

statsd.histogram('ai_pr_reviewer.review.duration', 15.3)
statsd.increment('ai_pr_reviewer.review.count')
```

**3. APM Tracing:**
```python
from ddtrace import tracer

@tracer.wrap(service="ai-pr-reviewer")
def review_pr(pr_id):
    # Automatic distributed tracing
    pass
```

**4. Alerts:**
- Failed reviews (>5 in 5 minutes)
- High token usage (>$10/day)
- Slow reviews (>30 seconds)

**Advantages:**
- ✅ No additional cost (using existing subscription)
- ✅ Unified monitoring with other services
- ✅ Rich dashboards and UX
- ✅ Team already familiar with Datadog
- ✅ Flexible alerting and APM tracing

---

## Resources NOT in Azure (But Part of Solution)

### Azure DevOps

**Not an Azure resource** - It's a separate Microsoft service
**Cost:** FREE (for up to 5 users)

**What we use:**
- Service Hooks (webhook configuration)
- Pull Request API (get PR details, post comments)
- Managed Identity authentication (via Azure AD)

**No additional Azure resources needed** - DevOps integration is via API only.

---

### OpenAI API

**Not an Azure resource** - External service  
**Alternative:** Azure AI Foundry (Azure-hosted)  
**Cost:** $0.01 per 1K tokens (GPT-4 Turbo)  

**Usage:**
- 100 PRs/month
- Avg 1,200 tokens per review (with diff-only)
- Total: 120,000 tokens/month = ~$1.20/month

**If using Azure AI Foundry instead:**
- Same pricing
- Stays within Azure boundary
- May have enterprise agreements/discounts

---

## Total Resource Count

### Azure Resources Created: **5**

1. ✅ Resource Group
2. ✅ Storage Account (with Table Storage)
3. ✅ Function App
4. ✅ App Service Plan (auto-created)
5. ✅ Key Vault

### External Services: **3**

6. Azure DevOps (Microsoft, separate from Azure)
7. OpenAI API (or Azure AI Foundry)
8. Datadog (your existing monitoring infrastructure)

---

## Cost Summary

### PoC/Development (100 PRs/month)

| Resource | Monthly Cost | Notes |
|----------|--------------|-------|
| **Azure Resources** | | |
| Resource Group | $0 | FREE |
| Storage Account | $1.00 | Functions + Table Storage |
| Function App (Consumption) | $0.10 | Pay per execution |
| App Service Plan | $0 | Included with Consumption |
| Key Vault | $0.50 | 3 secrets, minimal ops |
| **Azure Subtotal** | **$1.60** | |
| | | |
| **External Services** | | |
| OpenAI API (diff-only) | $8.00 | 120K tokens/month |
| Azure DevOps | $0 | FREE (up to 5 users) |
| Datadog | $0 | Using existing infrastructure |
| **External Subtotal** | **$8.00** | |
| | | |
| **TOTAL (PoC)** | **$9.60** | ~$10/month |

### Production (100 PRs/month, Premium Plan)

| Resource | Monthly Cost | Notes |
|----------|--------------|-------|
| Function App (Premium EP1) | $150.00 | No cold starts |
| Storage Account | $1.00 | Same as PoC |
| Key Vault | $0.50 | Same as PoC |
| OpenAI API | $8.00 | Same as PoC |
| Datadog | $0 | Existing infrastructure |
| **TOTAL (Production)** | **$159.50** | ~$160/month |

---

## Scaling Considerations

### When to Add More Resources

**100-500 PRs/month:**
- ✅ Current setup handles fine
- No changes needed

**500-1,000 PRs/month:**
- Consider Premium plan ($150/month)
- Better performance, no cold starts

**1,000-5,000 PRs/month:**
- Premium plan recommended
- Consider dedicated Storage Account for Tables
- Might need higher App Insights tier

**5,000+ PRs/month:**
- Premium plan with scale-out (2+ instances)
- Dedicated Storage Account for Tables
- Consider migrating to Cosmos DB for better query performance
- May need Azure Front Door for DDoS protection

---

## Resource Naming Convention

We follow Azure best practices:

| Resource Type | Prefix | Example |
|---------------|--------|---------|
| Resource Group | rg- | rg-ai-pr-reviewer |
| Storage Account | st | staiprreviewer (no hyphens) |
| Function App | func- | func-ai-pr-reviewer |
| Key Vault | kv- | kv-ai-pr-reviewer |

**Why?** Makes it easy to:
- Identify resource type at a glance
- Search and filter resources
- Apply consistent policies
- Follow Azure naming conventions

---

## Resource Dependencies

```
Resource Group
    └── Storage Account (created first)
          └── Function App (depends on Storage)
                └── App Service Plan (auto-created)
    └── Key Vault (independent)
          └── Access Policy → Function App Managed Identity
```

**Creation Order:**
1. Resource Group
2. Storage Account
3. Function App (creates App Service Plan automatically)
4. Key Vault
5. Storage Tables (in existing Storage Account)
6. Enable Managed Identity on Function App
7. Grant Key Vault and Table Storage access to Managed Identity

---

## Quick Deployment Checklist

### Phase 1: Infrastructure (30 minutes)

- [ ] Create Resource Group
- [ ] Create Storage Account
- [ ] Create Function App
- [ ] Create Key Vault
- [ ] Enable Managed Identity
- [ ] Grant Key Vault access
- [ ] Grant Table Storage access
- [ ] Create Table Storage tables

### Phase 2: Configuration (15 minutes)

- [ ] Store secrets in Key Vault
  - [ ] OpenAI API Key
  - [ ] Webhook Secret
- [ ] Configure Function App settings
  - [ ] Key Vault URL
  - [ ] Storage account name
  - [ ] DevOps organization
  - [ ] OpenAI model settings

### Phase 3: Deployment (15 minutes)

- [ ] Deploy Function code
- [ ] Test health endpoint
- [ ] Configure Azure DevOps webhook
- [ ] Test with sample PR
- [ ] Verify logs in Datadog

**Total Setup Time: ~1 hour**

---

## Resource Limits & Quotas

### Function App (Consumption Plan)

- Max execution time: 10 minutes (5 minutes default)
- Max concurrent executions: 200
- Max memory: 1.5 GB
- Max request size: 100 MB

### Storage Account

- Max storage capacity: 5 PB (petabytes)
- Max Table Storage ops: 20,000 per second
- Max tables: Unlimited
- Max entities per table: Unlimited

### Key Vault

- Max secrets: 25,000
- Max secret versions: Unlimited
- Max operations per 10 seconds: 2,000
- Max secret size: 25 KB

### Datadog

- Log retention: Per your Datadog plan
- Metrics retention: Per your Datadog plan
- APM tracing: Included in plan

**Our Usage:** Uses existing Datadog infrastructure ✅

---

## Cleanup Commands

**Delete everything:**
```bash
# Delete entire resource group (deletes all resources)
az group delete --name rg-ai-pr-reviewer --yes --no-wait

# Takes ~5 minutes
```

**Delete individual resources:**
```bash
# Function App
az functionapp delete --name func-ai-pr-reviewer --resource-group rg-ai-pr-reviewer

# Storage Account
az storage account delete --name staiprreviewer --resource-group rg-ai-pr-reviewer

# Key Vault (soft-delete enabled by default, recover within 90 days)
az keyvault delete --name kv-ai-pr-reviewer

# Permanently delete Key Vault (optional)
az keyvault purge --name kv-ai-pr-reviewer
```

---

## Summary

**Minimal Azure footprint:**
- Only 5 Azure resources (including auto-created App Service Plan)
- Simple architecture, easy to understand
- Low cost (~$10/month for PoC)
- Scales when needed

**All resources serve a clear purpose:**
- Storage Account: Function runtime + data storage (dual role)
- Function App: Your Python 3.12 application
- Key Vault: Secure secrets (zero secrets in code)
- Resource Group: Organizational container

**Monitoring via Datadog:**
- Uses existing infrastructure ($0 additional cost)
- Unified monitoring across all services
- Better dashboards and alerting than App Insights
- Team already familiar with tooling

**No unnecessary resources:**
- ❌ No dedicated database (using Table Storage in existing Storage Account)
- ❌ No Application Insights (using existing Datadog infrastructure)
- ❌ No API Management (Function URLs are sufficient)
- ❌ No VNet (can add later if needed)
- ❌ No Load Balancer (Functions auto-scales)
- ❌ No separate backup solution (Storage Account has built-in redundancy)

**Ready to deploy!** 🚀
