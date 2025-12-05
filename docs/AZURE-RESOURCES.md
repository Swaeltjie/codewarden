# Azure Resources Inventory

## Overview

CodeWarden requires **5 Azure resources** with a simple, cost-effective architecture.

### Resource Summary

| # | Resource | Purpose | Monthly Cost |
|---|----------|---------|--------------|
| 1 | Resource Group | Logical container | FREE |
| 2 | Storage Account | Functions runtime + Table Storage | $1.00 |
| 3 | Function App | Python 3.12 application | $0.10-150* |
| 4 | App Service Plan | Hosting (auto-created) | FREE* |
| 5 | Key Vault | Secure secrets | $0.50 |
| **Total (Dev)** | | | **~$2/month** |
| **Total (Prod)** | | | **~$160/month** |

*Consumption plan: $0.10/month for 100 PRs. Production Premium plan: $150/month.

**Monitoring:** Uses your existing Datadog infrastructure ($0 additional cost).

---

## Resource Details

### 1. Resource Group
**Name:** `rg-ai-pr-reviewer`
**Purpose:** Container for all resources
**Cost:** FREE

```bash
az group create \
  --name rg-ai-pr-reviewer \
  --location eastus
```

### 2. Storage Account (Dual Role)
**Name:** `staiprreviewer` (globally unique)
**SKU:** Standard_LRS
**Cost:** ~$1/month

**Serves two purposes:**
- **Functions Runtime:** Stores function code and state
- **Data Storage:** Table Storage for feedback and history

**Tables Created:**
- `feedback` - Developer feedback tracking
- `reviewhistory` - PR review history

```bash
# Create Storage Account
az storage account create \
  --name staiprreviewer \
  --resource-group rg-ai-pr-reviewer \
  --location eastus \
  --sku Standard_LRS \
  --kind StorageV2

# Create tables
az storage table create --name feedback --account-name staiprreviewer
az storage table create --name reviewhistory --account-name staiprreviewer
```

**Why Table Storage?**
- **10-20x cheaper** than Cosmos DB ($0.10 vs $1-25/month)
- Perfect for simple key-value queries
- Part of existing Storage Account
- Fast enough (sub-100ms)

### 3. Function App
**Name:** `func-ai-pr-reviewer`
**Runtime:** Python 3.12, Functions v4, Linux
**Cost:** $0.10/month (Flex Consumption) or $150/month (Premium)

**Contains 6 functions:**
1. `pr-webhook` (HTTP) - Receives PR webhooks
2. `feedback-collector` (Timer) - Runs hourly
3. `pattern-detector` (Timer) - Runs daily at 2 AM
4. `health` (HTTP) - Health check endpoint
5. `reliability-health` (HTTP) - Reliability metrics
6. `circuit-breaker-admin` (HTTP) - Circuit breaker management

```bash
# Flex Consumption (Recommended)
az functionapp create \
  --resource-group rg-ai-pr-reviewer \
  --name func-ai-pr-reviewer \
  --storage-account staiprreviewer \
  --flexconsumption-location eastus \
  --runtime python \
  --runtime-version 3.12 \
  --functions-version 4
```

**Note:** Linux Consumption plan reaches EOL September 30, 2028. Use Flex Consumption for new deployments.

**Flex Consumption Supported Python Versions:** 3.10, 3.11, 3.12

**Hosting Plan Comparison:**

| Feature | Flex Consumption | Premium EP1 |
|---------|------------------|-------------|
| Cost | $0.10/100 PRs | $150/month fixed |
| Cold start | Reduced (~1s) | None |
| Scale | 0-1000 instances | Always-warm |
| Private networking | Supported | Supported |
| Best for | Dev/PoC/Production | High-traffic production |

### 4. Key Vault
**Name:** `kv-ai-pr-reviewer`
**Cost:** ~$0.50/month

**Stores secrets securely:**
- `OPENAI-API-KEY` - AI API key
- `WEBHOOK-SECRET` - Webhook validation

**Access:** Function App uses Managed Identity (no credentials!)

```bash
# Create Key Vault (RBAC enabled by default)
az keyvault create \
  --name kv-ai-pr-reviewer \
  --resource-group rg-ai-pr-reviewer \
  --location eastus

# Grant Function App access (using RBAC)
PRINCIPAL_ID=$(az functionapp identity show \
  --name func-ai-pr-reviewer \
  --resource-group rg-ai-pr-reviewer \
  --query principalId -o tsv)

KEYVAULT_ID=$(az keyvault show \
  --name kv-ai-pr-reviewer \
  --resource-group rg-ai-pr-reviewer \
  --query id -o tsv)

az role assignment create \
  --assignee $PRINCIPAL_ID \
  --role "Key Vault Secrets User" \
  --scope $KEYVAULT_ID
```

---

## External Services (Not Azure Resources)

### Azure DevOps
**Cost:** FREE (up to 5 users)
**Integration:** REST API with Managed Identity authentication

### OpenAI API
**Cost:** ~$8/month for 100 PRs with diff-only analysis
**Alternative:** Azure AI Foundry (same pricing)

### Datadog
**Cost:** $0 (using existing infrastructure)
**Savings vs Application Insights:** $2-5/month

---

## Complete Cost Breakdown

### Development/PoC (100 PRs/month)

| Component | Monthly Cost |
|-----------|--------------|
| **Azure Infrastructure** | |
| Storage Account | $1.00 |
| Function App (Consumption) | $0.10 |
| Key Vault | $0.50 |
| **Azure Total** | **$1.60** |
| | |
| **External Services** | |
| OpenAI API | $8.00 |
| Azure DevOps | $0 |
| Datadog | $0 |
| **External Total** | **$8.00** |
| | |
| **TOTAL** | **~$10/month** |

### Production (100 PRs/month, Premium Plan)

| Component | Monthly Cost |
|-----------|--------------|
| Function App (Premium EP1) | $150.00 |
| Storage Account | $1.00 |
| Key Vault | $0.50 |
| OpenAI API | $8.00 |
| **TOTAL** | **~$160/month** |

**vs Alternatives:**
- CodeRabbit: $380-780/month
- GitHub Copilot: $200-780/month
- **CodeWarden: $10-160/month** (3-78x cheaper)

---

## Resource Naming Convention

| Resource Type | Prefix | Example |
|---------------|--------|---------|
| Resource Group | rg- | rg-ai-pr-reviewer |
| Storage Account | st | staiprreviewer (no hyphens) |
| Function App | func- | func-ai-pr-reviewer |
| Key Vault | kv- | kv-ai-pr-reviewer |

---

## Deployment Checklist

### Infrastructure (30 minutes)
- [ ] Create Resource Group
- [ ] Create Storage Account
- [ ] Create Function App
- [ ] Create Key Vault
- [ ] Enable Managed Identity
- [ ] Grant Key Vault access
- [ ] Grant Table Storage access (Storage Table Data Contributor role)
- [ ] Create Table Storage tables

### Configuration (15 minutes)
- [ ] Store secrets in Key Vault
- [ ] Configure Function App settings
- [ ] Add Managed Identity to Azure DevOps

### Deployment (15 minutes)
- [ ] Deploy Function code
- [ ] Test health endpoint
- [ ] Configure Azure DevOps webhook
- [ ] Test with sample PR
- [ ] Verify logs in Datadog

**Total Setup Time: ~1 hour**

---

## Scaling Considerations

| PRs/Month | Recommendation | Changes Needed |
|-----------|----------------|----------------|
| 100-500 | Current setup | None |
| 500-1,000 | Premium plan | Better performance |
| 1,000-5,000 | Premium + scale-out | 2+ instances |
| 5,000+ | Premium + Cosmos DB | Global scale |

---

## Resource Dependencies

```
Resource Group
├── Storage Account (create first)
│   ├── Table: feedback
│   └── Table: reviewhistory
├── Function App (depends on Storage)
│   └── Managed Identity
└── Key Vault
    └── Access Policy → Function App MI
```

**Creation Order:**
1. Resource Group
2. Storage Account
3. Function App (creates App Service Plan automatically)
4. Key Vault
5. Enable Managed Identity
6. Grant permissions
7. Create tables

---

## Cleanup

**Delete everything:**
```bash
az group delete --name rg-ai-pr-reviewer --yes --no-wait
```

**Delete Key Vault permanently:**
```bash
az keyvault purge --name kv-ai-pr-reviewer
```

---

## Summary

**Minimal footprint:**
- Only 5 Azure resources (including auto-created App Service Plan)
- Simple architecture, easy to manage
- Low cost (~$10/month for PoC, ~$160/month for production)

**Smart design choices:**
- Storage Account serves dual role (runtime + data)
- Table Storage instead of Cosmos DB (10-20x cheaper)
- Existing Datadog infrastructure (no additional monitoring costs)
- Managed Identity for security (zero credentials in code)

**No unnecessary resources:**
- ❌ No Application Insights (using Datadog)
- ❌ No API Management (Functions sufficient)
- ❌ No VNet (can add later if needed)
- ❌ No Load Balancer (auto-scales)

**Ready to deploy!** See [DEPLOYMENT-GUIDE.md](DEPLOYMENT-GUIDE.md) for step-by-step instructions.
