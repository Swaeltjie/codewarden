# Managed Identity Setup Guide

This guide explains how CodeWarden uses Managed Identity for secure, credential-free authentication to Azure services.

## Overview

CodeWarden uses **System-assigned Managed Identity** to authenticate to Azure services without storing any credentials. This is more secure than using connection strings or service principals.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Azure Function App                        │
│                  (CodeWarden Reviewer)                       │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │         System-assigned Managed Identity           │    │
│  │  (Automatically managed by Azure - no secrets!)    │    │
│  └────────────────────────────────────────────────────┘    │
│                          │                                   │
│              Uses DefaultAzureCredential()                   │
│                          │                                   │
└──────────────────────────┼───────────────────────────────────┘
                           │
           ┌───────────────┼───────────────┐
           │               │               │
           ▼               ▼               ▼
    ┌──────────┐   ┌─────────────┐  ┌──────────┐
    │   Key    │   │   Table     │  │  Azure   │
    │  Vault   │   │  Storage    │  │  DevOps  │
    └──────────┘   └─────────────┘  └──────────┘
         │                │               │
         │                │               │
         ▼                ▼               ▼
    Stores API      RBAC Roles      Azure AD
    Keys (OpenAI)   (Contributor)    Bearer Token
```

## Authentication Methods by Service

| Service | Authentication Method | Why |
|---------|----------------------|-----|
| **Key Vault** | ✅ Managed Identity | Fully supported, no credentials needed |
| **Table Storage** | ✅ Managed Identity | RBAC roles, replaces connection strings |
| **Azure DevOps API** | ✅ Managed Identity | Azure AD Bearer tokens, no credentials |
| **OpenAI/Azure OpenAI** | 🔑 API Key | External service, stored in Key Vault |

## Setup Instructions

### 1. Enable System-assigned Managed Identity

```bash
# Enable Managed Identity on your Function App
az functionapp identity assign \
  --name <function-app-name> \
  --resource-group <resource-group>

# Get the Managed Identity Object ID (Principal ID)
PRINCIPAL_ID=$(az functionapp identity show \
  --name <function-app-name> \
  --resource-group <resource-group> \
  --query principalId -o tsv)

echo "Managed Identity Principal ID: $PRINCIPAL_ID"
```

### 2. Grant Key Vault Permissions

```bash
# Grant the Function App access to Key Vault secrets
az keyvault set-policy \
  --name <keyvault-name> \
  --object-id $PRINCIPAL_ID \
  --secret-permissions get list

# Verify permissions
az keyvault show \
  --name <keyvault-name> \
  --query "properties.accessPolicies[?objectId=='$PRINCIPAL_ID']"
```

**Secrets stored in Key Vault:**
- `OPENAI-API-KEY` - OpenAI API key (or `AZURE-OPENAI-KEY` for Azure OpenAI)
- `WEBHOOK-SECRET` - Secret for validating incoming webhooks from Azure DevOps

### 3. Grant Table Storage Permissions

```bash
# Get the Storage Account name
STORAGE_ACCOUNT="<your-storage-account-name>"

# Grant "Storage Table Data Contributor" role
az role assignment create \
  --assignee $PRINCIPAL_ID \
  --role "Storage Table Data Contributor" \
  --scope "/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.Storage/storageAccounts/$STORAGE_ACCOUNT"

# Verify role assignment
az role assignment list \
  --assignee $PRINCIPAL_ID \
  --scope "/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.Storage/storageAccounts/$STORAGE_ACCOUNT"
```

### 4. Configure Function App Settings

```bash
# Set required environment variables
az functionapp config appsettings set \
  --name <function-app-name> \
  --resource-group <resource-group> \
  --settings \
    KEYVAULT_URL="https://<keyvault-name>.vault.azure.net/" \
    AZURE_STORAGE_ACCOUNT_NAME="<storage-account-name>" \
    AZURE_DEVOPS_ORG="<your-org-name>" \
    OPENAI_MODEL="gpt-4o" \
    LOG_LEVEL="INFO" \
    ENVIRONMENT="production"
```

**Notice**: No connection strings or credentials in app settings!

### 5. Add Managed Identity to Azure DevOps

Follow the detailed guide in `AZURE-DEVOPS-MANAGED-IDENTITY.md` to:
1. Add the Managed Identity to your Azure DevOps organization
2. Grant appropriate permissions (Code: Read, PR Threads: Contribute)

This provides credential-free, never-expiring authentication to Azure DevOps.

## Local Development Setup

For local development, use one of these methods:

### Option 1: Azure CLI (Recommended)

```bash
# Login to Azure CLI
az login

# The app will use your Azure CLI credentials via DefaultAzureCredential
# No additional setup needed!
```

### Option 2: Environment Variables (Fallback)

Create a `.env` file:

```bash
# Azure Configuration
KEYVAULT_URL=https://<keyvault-name>.vault.azure.net/
AZURE_STORAGE_ACCOUNT_NAME=<storage-account-name>
AZURE_DEVOPS_ORG=<your-org>

# AI Configuration
OPENAI_MODEL=gpt-4o
OPENAI_MAX_TOKENS=4000

# Application
LOG_LEVEL=DEBUG
ENVIRONMENT=development
```

**For local testing only**, you can temporarily use connection strings:
- Set `AZURE_STORAGE_CONNECTION_STRING` in `.env` (not recommended for production)

## How DefaultAzureCredential Works

The app uses `DefaultAzureCredential()` which tries authentication methods in this order:

1. **Environment Variables** (for local dev with service principal)
2. **Managed Identity** (in Azure - production)
3. **Visual Studio Code** (local dev)
4. **Azure CLI** (local dev - recommended)
5. **Azure PowerShell** (local dev)

This means:
- ✅ In Azure: Automatically uses Managed Identity
- ✅ Locally: Uses your Azure CLI login
- ✅ No credentials in code or config files

## Security Benefits

### Before (Connection Strings & Keys)
```bash
# ❌ Credentials exposed in app settings
AZURE_STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=https;AccountName=...;AccountKey=VERY_LONG_SECRET_KEY;..."

# ❌ Risk: Leaked in logs, environment dumps, or misconfigured access
# ❌ Manual rotation required
# ❌ Stored in multiple locations
```

### After (Managed Identity)
```bash
# ✅ No credentials in app settings
AZURE_STORAGE_ACCOUNT_NAME="mystorageaccount"
KEYVAULT_URL="https://mykeyvault.vault.azure.net/"

# ✅ Secrets stored only in Key Vault
# ✅ Access controlled by Azure RBAC
# ✅ Automatic credential rotation (for Managed Identity)
```

## Troubleshooting

### "Authentication failed" errors in Azure

1. **Verify Managed Identity is enabled:**
   ```bash
   az functionapp identity show \
     --name <function-app-name> \
     --resource-group <resource-group>
   ```

2. **Check Key Vault permissions:**
   ```bash
   az keyvault show \
     --name <keyvault-name> \
     --query "properties.accessPolicies[?objectId=='$PRINCIPAL_ID']"
   ```

3. **Check Table Storage permissions:**
   ```bash
   az role assignment list \
     --assignee $PRINCIPAL_ID \
     --all
   ```

### Local development authentication issues

1. **Ensure you're logged in to Azure CLI:**
   ```bash
   az login
   az account show
   ```

2. **Check your Azure CLI has access to Key Vault:**
   ```bash
   az keyvault secret show \
     --vault-name <keyvault-name> \
     --name "OPENAI-API-KEY"
   ```

### "Storage Table Data Contributor" role not working

Wait 5-10 minutes after role assignment for Azure RBAC to propagate.

## Required Azure RBAC Roles

| Service | Role | Scope |
|---------|------|-------|
| Key Vault | Key Vault Secrets User (or access policy) | Key Vault |
| Table Storage | Storage Table Data Contributor | Storage Account |
| Azure DevOps | Basic License + Project Permissions | Organization/Project |

## Migrating from Connection Strings

If you're upgrading from connection strings:

1. **Enable Managed Identity** (see step 1 above)
2. **Grant permissions** (steps 2-3)
3. **Update app settings:**
   ```bash
   # Remove old settings
   az functionapp config appsettings delete \
     --name <function-app-name> \
     --resource-group <resource-group> \
     --setting-names AZURE_STORAGE_CONNECTION_STRING

   # Add new settings
   az functionapp config appsettings set \
     --name <function-app-name> \
     --resource-group <resource-group> \
     --settings AZURE_STORAGE_ACCOUNT_NAME="<storage-account-name>"
   ```
4. **Restart function app**
5. **Verify logs** for successful authentication

## References

- [Azure Managed Identities](https://learn.microsoft.com/en-us/azure/active-directory/managed-identities-azure-resources/overview)
- [DefaultAzureCredential](https://learn.microsoft.com/en-us/dotnet/api/azure.identity.defaultazurecredential)
- [Azure DevOps Managed Identity Auth](https://learn.microsoft.com/en-us/azure/devops/integrate/get-started/authentication/service-principal-managed-identity)
- [Azure Storage RBAC](https://learn.microsoft.com/en-us/azure/storage/common/authorize-data-access)
