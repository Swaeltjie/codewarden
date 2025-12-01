# Deployment Guide

## Prerequisites

- Python 3.12+
- Azure CLI
- Azure Functions Core Tools v4
- Git
- Datadog account (optional, for monitoring)

---

## Local Development Setup

### 1. Clone and Install

```bash
# Clone repository
git clone <your-repo>
cd codewarden

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Install pre-commit hooks
pre-commit install
```

### 2. Local Configuration

**Authentication:** Login to Azure CLI (uses Managed Identity locally):

```bash
az login
az account set --subscription <your-subscription-id>
```

**Create `.env` file:**
```bash
# .env (local development only - DO NOT COMMIT)

# Azure Configuration (no credentials needed - uses Azure CLI login)
KEYVAULT_URL=https://your-keyvault.vault.azure.net/
AZURE_STORAGE_ACCOUNT_NAME=your-storage-account
AZURE_DEVOPS_ORG=your-org

# AI Configuration
OPENAI_MODEL=gpt-4o
OPENAI_MAX_TOKENS=4000

# Application
LOG_LEVEL=DEBUG
ENVIRONMENT=development
```

**Note:** Secrets (API keys, webhook secrets) are stored in Key Vault and accessed via Managed Identity. No credentials in `.env`!

### 3. Run Locally

```bash
# Start Azure Functions runtime
func start

# Available endpoints:
# http://localhost:7071/api/pr-webhook
# http://localhost:7071/api/health
```

### 4. Run Tests & Code Quality

```bash
# Run all tests with coverage
pytest --cov=src --cov-report=html

# Format and lint
black src/
ruff check src/ --fix
mypy src/

# Security scan
bandit -r src/

# Run all checks
pre-commit run --all-files
```

---

## Azure Deployment

### 1. Create Azure Resources

```bash
# Login to Azure
az login
az account set --subscription "<your-subscription>"

# Set variables
RESOURCE_GROUP="rg-ai-pr-reviewer"
LOCATION="eastus"
FUNCTION_APP="func-ai-pr-reviewer"
STORAGE_ACCOUNT="staiprreviewer"
KEYVAULT_NAME="kv-ai-pr-reviewer"

# Create resource group
az group create --name $RESOURCE_GROUP --location $LOCATION

# Create storage account
az storage account create \
  --name $STORAGE_ACCOUNT \
  --location $LOCATION \
  --resource-group $RESOURCE_GROUP \
  --sku Standard_LRS \
  --kind StorageV2

# Create Table Storage tables
az storage table create --name feedback --account-name $STORAGE_ACCOUNT
az storage table create --name reviewhistory --account-name $STORAGE_ACCOUNT

# Create Function App (Python 3.12, Consumption plan)
az functionapp create \
  --resource-group $RESOURCE_GROUP \
  --consumption-plan-location $LOCATION \
  --runtime python \
  --runtime-version 3.12 \
  --functions-version 4 \
  --name $FUNCTION_APP \
  --storage-account $STORAGE_ACCOUNT \
  --os-type Linux

# Create Key Vault
az keyvault create \
  --name $KEYVAULT_NAME \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION
```

### 2. Enable Managed Identity

```bash
# Enable system-assigned managed identity
az functionapp identity assign \
  --name $FUNCTION_APP \
  --resource-group $RESOURCE_GROUP

# Get the principal ID
PRINCIPAL_ID=$(az functionapp identity show \
  --name $FUNCTION_APP \
  --resource-group $RESOURCE_GROUP \
  --query principalId -o tsv)

# Grant Key Vault access
az keyvault set-policy \
  --name $KEYVAULT_NAME \
  --object-id $PRINCIPAL_ID \
  --secret-permissions get list

# Grant Table Storage access
az role assignment create \
  --assignee $PRINCIPAL_ID \
  --role "Storage Table Data Contributor" \
  --scope "/subscriptions/$(az account show --query id -o tsv)/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Storage/storageAccounts/$STORAGE_ACCOUNT"
```

### 3. Store Secrets in Key Vault

```bash
# Store OpenAI API Key
az keyvault secret set \
  --vault-name $KEYVAULT_NAME \
  --name "OPENAI-API-KEY" \
  --value "your-actual-openai-key"

# Store webhook secret
az keyvault secret set \
  --vault-name $KEYVAULT_NAME \
  --name "WEBHOOK-SECRET" \
  --value "$(openssl rand -hex 32)"
```

### 4. Configure Function App Settings

```bash
# Get Key Vault URI
KEYVAULT_URI="https://${KEYVAULT_NAME}.vault.azure.net/"

# Set application settings
az functionapp config appsettings set \
  --name $FUNCTION_APP \
  --resource-group $RESOURCE_GROUP \
  --settings \
    KEYVAULT_URL=$KEYVAULT_URI \
    AZURE_STORAGE_ACCOUNT_NAME=$STORAGE_ACCOUNT \
    AZURE_DEVOPS_ORG=your-org \
    OPENAI_MODEL=gpt-4o \
    OPENAI_MAX_TOKENS=4000 \
    LOG_LEVEL=INFO \
    ENVIRONMENT=production
```

**Note:** Application Insights is NOT configured (you're using Datadog). See [DATADOG-INTEGRATION.md](DATADOG-INTEGRATION.md) for logging setup.

### 5. Deploy Function Code

```bash
# Deploy using Azure Functions Core Tools
func azure functionapp publish $FUNCTION_APP --python

# Or deploy using Azure CLI with zip
az functionapp deployment source config-zip \
  --name $FUNCTION_APP \
  --resource-group $RESOURCE_GROUP \
  --src codewarden.zip
```

### 6. Get Function URL

```bash
# Get the function URL with access key
FUNCTION_URL=$(az functionapp function show \
  --name $FUNCTION_APP \
  --resource-group $RESOURCE_GROUP \
  --function-name pr-webhook \
  --query 'invokeUrlTemplate' -o tsv)

FUNCTION_KEY=$(az functionapp keys list \
  --name $FUNCTION_APP \
  --resource-group $RESOURCE_GROUP \
  --query 'functionKeys.default' -o tsv)

echo "Webhook URL: ${FUNCTION_URL}?code=${FUNCTION_KEY}"
```

---

## Azure DevOps Configuration

### 1. Add Managed Identity to Azure DevOps

Follow the detailed setup in [AZURE-DEVOPS-MANAGED-IDENTITY.md](AZURE-DEVOPS-MANAGED-IDENTITY.md):

1. Get Managed Identity Object ID from Function App
2. Add MI to Azure DevOps organization (Basic license)
3. Grant project permissions:
   - Code: Reader
   - Pull Request Threads: Contributor
   - Project: Reader

### 2. Create Service Hook

1. Go to Project Settings → Service Hooks
2. Click "Create Subscription"
3. Select "Web Hooks"
4. Configure:
   - **Trigger:** Pull request created OR updated
   - **URL:** Your Function URL (from step 6 above)
   - **HTTP Headers:**
     ```
     x-webhook-secret: <secret-from-keyvault>
     Content-Type: application/json
     ```
5. Test the connection
6. Save

---

## Monitoring & Troubleshooting

### View Logs

```bash
# Stream live logs from Azure
func azure functionapp logstream $FUNCTION_APP

# Or use Azure CLI
az webapp log tail --name $FUNCTION_APP --resource-group $RESOURCE_GROUP
```

### Datadog Integration (Recommended)

See [DATADOG-INTEGRATION.md](DATADOG-INTEGRATION.md) for complete setup.

**Quick setup:**
1. Install Datadog Azure integration
2. Configure log forwarding
3. Set up custom metrics and dashboards
4. Create alerts for failures

### Health Check

```bash
# Check function health
curl https://${FUNCTION_APP}.azurewebsites.net/api/health
```

---

## CI/CD Pipeline (GitHub Actions)

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to Azure Functions

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Run tests
        run: pytest

      - name: Run linting
        run: ruff check src/

      - name: Type checking
        run: mypy src/

  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Login to Azure
        uses: azure/login@v1
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}

      - name: Deploy to Azure Functions
        run: |
          func azure functionapp publish ${{ secrets.FUNCTION_APP_NAME }} --python
```

---

## Security Checklist

- [x] Secrets in Key Vault (not environment variables)
- [x] Managed Identity enabled
- [x] Function key required for HTTP trigger
- [x] Webhook secret validation
- [x] HTTPS only
- [x] RBAC permissions (principle of least privilege)

---

## Cost Optimization

### Consumption Plan Pricing

- First 1M executions: **FREE**
- After: $0.20 per million executions
- Memory: $0.000016/GB-s

### Estimated Monthly Costs (100 PRs/month)

| Resource | Monthly Cost |
|----------|--------------|
| Function App (Consumption) | $0.10 |
| Storage Account | $1.00 |
| Key Vault | $0.50 |
| OpenAI API (diff-only) | $8.00 |
| Datadog | $0 (existing) |
| **TOTAL** | **~$10/month** |

### Cost-Saving Tips

1. ✅ Use existing Datadog (vs Application Insights: $2-5/month saved)
2. ✅ Use Table Storage (vs Cosmos DB: $1-2/month saved)
3. ✅ Use diff-only analysis (88% token savings)
4. ✅ Use Consumption plan (pay per execution)

---

## Troubleshooting Common Issues

### Cold Start Too Slow
**Solution:** Use Premium plan (~$150/month) for always-ready instances

### Key Vault Access Denied
```bash
# Verify managed identity has access
az keyvault show --name $KEYVAULT_NAME --query properties.accessPolicies

# Re-grant access
az keyvault set-policy \
  --name $KEYVAULT_NAME \
  --object-id $PRINCIPAL_ID \
  --secret-permissions get list
```

### Function Timeout
**Solution:** Increase timeout in `host.json`:
```json
{
  "functionTimeout": "00:10:00"
}
```

---

## Next Steps

1. ✅ Deploy to Azure
2. ✅ Configure Azure DevOps webhook
3. ✅ Test with a sample PR
4. ✅ Monitor logs in Datadog
5. ✅ Set up alerting

**Your CodeWarden deployment is production-ready!** 🚀

For advanced features, see:
- [MANAGED-IDENTITY-SETUP.md](MANAGED-IDENTITY-SETUP.md) - Complete MI configuration
- [DATADOG-INTEGRATION.md](DATADOG-INTEGRATION.md) - Advanced monitoring
- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture details
